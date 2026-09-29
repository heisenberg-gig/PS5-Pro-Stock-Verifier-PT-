#!/usr/bin/env python3
"""
Monitor de stock da PlayStation 5 Pro em varias lojas portuguesas:
MEO, Worten, Radio Popular, Darty (MediaMarkt), GlobalData
e PcComponentes.

Usa o Chrome (via Playwright) em modo headless para carregar cada
pagina como um browser real e envia uma notificacao para o telemovel
via ntfy.sh assim que detectar stock disponivel numa loja.

Na Worten, ignora especificamente stock vendido por revendedores do
marketplace -- so notifica quando for a propria Worten a vender.

Requisitos (correr uma vez):
    pip install playwright
    python -m playwright install chromium

Uso:
    python meo_ps5pro_watcher.py
"""

import random
import time
import logging
import sys
from datetime import datetime
from dataclasses import dataclass, field

import urllib.request
import urllib.error
import subprocess
import threading
import platform
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

# ----------------------------------------------------------------------
# CONFIGURACAO -- ajusta aqui
# ----------------------------------------------------------------------

# Topico do ntfy.sh -- escolhe um nome UNICO e dificil de adivinhar,
# porque qualquer pessoa que souber o nome do topico pode ler as tuas
# notificacoes ou enviar-te notificacoes falsas.
# Ex: "ps5pro-stock_xasdas"
NTFY_TOPIC = "INSERE-AQUI-O-TOPICO"

# Intervalo entre verificacoes de CADA loja, em segundos.
# E gerado um valor aleatorio entre MIN e MAX de cada vez, para o
# padrao de pedidos nao parecer robotico. Como ha varias lojas, o watcher
# vai alternando entre elas, por isso cada loja individual acaba por
# ser verificada com uma cadencia um pouco mais espacada do que isto.
CHECK_INTERVAL_MIN = 45    # 45 segundos
CHECK_INTERVAL_MAX = 90    # 1.5 minutos

# Depois de notificar que ha stock numa loja, esperar este tempo antes
# de voltar a notificar sobre essa MESMA loja (evita spam se oscilar
# in/out stock)
RENOTIFY_COOLDOWN_SECONDS = 15 * 60  # 15 minutos

# Notificacao nativa + som no PC (alem do telemovel via ntfy)
DESKTOP_NOTIFICATIONS = True   # toast do sistema (Windows / Mac / Linux)
DESKTOP_SOUND = True           # apita no PC quando ha stock
SOUND_REPEATS = 8              # quantas vezes repete o alarme (stock)
SOUND_REPEATS_WARNING = 2      # repeticoes para avisos (erros)

# User-Agent realista (Chrome recente em Windows)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

LOG_FILE = "meo_ps5pro_watcher.log"

# Browser usado pelo Playwright. None = Chromium do Playwright (por defeito).
# "chrome" = usa o Google Chrome instalado no PC, que costuma ser bloqueado
# bastante menos pelas lojas (PcComponentes). Experimenta se houver erros
# de "pagina bloqueada por anti-bot".
BROWSER_CHANNEL = None


# Historico de mudancas de estado (sem stock <-> com stock).
# As mudancas ficam no LOG_FILE (linhas com "MUDANCA DE ESTADO") e, para
# cada mudanca, guarda-se um snapshot da pagina na pasta abaixo.
SNAPSHOT_DIR = "snapshots"
STATE_FILE = "estado_lojas.json"   # lembra o ultimo estado entre reinicios
SNAPSHOT_MAX_CHARS = 20000         # limite de texto guardado por snapshot
SCREENSHOT_ON_CHANGE = True        # tira foto (PNG) da pagina em cada mudanca de estado
SCREENSHOT_FULL_PAGE = False       # True = pagina inteira; False = so a parte visivel (mais leve)
SAVE_POPUP_DEBUG_HTML = False      # True = guarda um .html de diagnostico quando um popup nao fecha (normalmente deixar False)

# ----------------------------------------------------------------------
# DEFINICAO DAS LOJAS
# ----------------------------------------------------------------------

GENERIC_OUT_OF_STOCK_MARKERS = [
    "out of stock",
    "esgotado",
    "produto indisponível",
    "produto indisponivel",
    "indisponível",
    "indisponivel",
    "sem stock",
    "rutura de stock",
    "notifica-me quando disponível",
    "avisem-me",
]

GENERIC_BUY_BUTTON_SELECTORS = (
    "button:has-text('Comprar'), button:has-text('Buy'), "
    "button:has-text('Adicionar ao carrinho'), button:has-text('Add to cart'), "
    "button:has-text('Adicionar ao cesto')"
)


@dataclass
class StoreResult:
    in_stock: bool
    detail: str
    page_text: str = field(default="", repr=False)   # texto da pagina (para snapshot)
    screenshot: bytes = field(default=b"", repr=False)  # foto da pagina (PNG), em memoria


@dataclass
class Store:
    name: str
    url: str
    checker: callable
    last_notified_at: float = field(default=0.0, repr=False)


# ----------------------------------------------------------------------
# FECHAR AVISOS (cookies, popups promocionais)
# ----------------------------------------------------------------------
# Cada entrada e um seletor Playwright. Sao tentados por ordem e clica-se
# em TODOS os que estiverem visiveis. Preferimos "rejeitar / continuar sem
# aceitar" sempre que existe (menos cookies de tracking); quando a loja so
# oferece "aceitar", clica-se nesse.
# Se uma loja mudar o texto dos botoes, e so acrescentar/ajustar aqui.

# Ordem importa: a funcao para no primeiro grupo que fechar um aviso.
#   Grupo 1 = RECUSAR / continuar sem aceitar (preferido)
#   Grupo 2 = fechar popups promocionais (botao X)
#   Grupo 3 = ACEITAR (so se a loja nao deixar recusar)
POPUP_SELECTOR_GROUPS = [
    # ---- Grupo 1: recusar ----
    [
        "a:has-text('Continuar sem aceitar')",                  # Darty
        "button:has-text('Continuar sem aceitar')",
        "button:has-text('Rejeitar cookies')",                  # Worten
        "a:has-text('Rejeitar cookies')",
        "text=/^\\s*Negar\\s*$/i",                              # Radio Popular (pode nao ser <button>)
        "button:has-text('Negar')",
        "#onetrust-reject-all-handler",
        "button:has-text('Rejeitar todos')",
        "button:has-text('Recusar')",
        "#CybotCookiebotDialogBodyButtonDecline",               # GlobalData (Cookiebot): "Tecnicamente necessario"
        "button:has-text('Tecnicamente necessário')",
        "button:has-text('Tecnicamente necessario')",
    ],
    # ---- Grupo 2: popups promocionais ----
    # (os icones/botoes "x" dos popups sao tratados a parte, em
    #  _close_promo_popup(), que corre SEMPRE antes destes grupos)
    [
        "button[aria-label='Close']",
        "button[aria-label='Fechar']",
    ],
    # ---- Grupo 3: aceitar (ultimo recurso) ----
    [
        "button:has-text('CONCORDO')",                          # MEO (so tem "Concordo" / "Mais opcoes")
        "button:has-text('Concordo')",
        "button:has-text('ACEITAR TODOS OS COOKIES')",          # Darty
        "#onetrust-accept-btn-handler",
        "button:has-text('Aceitar todos')",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",  # GlobalData (Cookiebot)
        "button:has-text('Permitir todos')",
    ],
]

# Pequenos "x" de popups que nao tem texto (ex.: Clube RP+). Tentamos,
# por esta ordem: (1) seletores de botao/icone de fechar, (2) glifos de texto.
POPUP_CLOSE_GLYPHS = ["\u00d7", "\u2715", "\u2716", "X"]

# Seletores CSS de botoes de fechar SEM texto (icones SVG/imagem). Sao
# procurados apenas DENTRO de um modal/popup/dialogo, para nao clicar em
# "x" de outras coisas da pagina (ex.: limpar a caixa de pesquisa).
POPUP_CLOSE_ICON_SELECTORS = [
    # --- Radio Popular (Clube RP+): o popup e uma imagem "wpst-hero-image"
    #     e o "x" e um irmao/primo dela, dentro do mesmo contentor.
    ".wpst-hero-image ~ [class*='close' i]",
    ".wpst-hero-image ~ button",
    ".wpst-hero-image ~ [role='button']",
    ":has(> .wpst-hero-image) > [class*='close' i]",
    ":has(> .wpst-hero-image) > button",
    "[class*='wpst' i] [class*='close' i]",
    "[class*='wpst' i] [aria-label*='fech' i]",
    "[class*='wpst' i] [aria-label*='clos' i]",
    "[role='dialog'] [class*='close' i]",
    "[role='dialog'] [aria-label*='clos' i]",
    "[role='dialog'] [aria-label*='fech' i]",
    "[aria-modal='true'] [class*='close' i]",
    "[class*='modal' i] [class*='close' i]",
    "[class*='popup' i] [class*='close' i]",
    "[class*='overlay' i] [class*='close' i]",
    "[class*='modal' i] [aria-label*='clos' i]",
    "[class*='popup' i] [aria-label*='fech' i]",
    "[id*='modal' i] [class*='close' i]",
    "[id*='popup' i] [class*='close' i]",
    "[id*='modal' i] [aria-label*='clos' i]",
    "[id*='modal' i] [aria-label*='fech' i]",
    "[id*='popup' i] [aria-label*='fech' i]",
]


def _click_no_scroll(page: Page, el) -> bool:
    """
    Clica num elemento SEM fazer scroll da pagina.

    O click() normal do Playwright faz scroll ate ao elemento. Em paginas
    onde o banner de cookies esta no fim do documento (MEO), isso arrastava
    a pagina para o rodape. Aqui despachamos o evento de clique directamente
    (nao mexe no scroll) e, se isso nao resultar, usamos o click() normal.
    """
    try:
        el.dispatch_event("click", timeout=1500)
        return True
    except Exception:
        pass
    try:
        el.click(timeout=1500, force=True)
        return True
    except Exception:
        return False


def _click_first_visible(page: Page, selector: str) -> bool:
    """Clica no primeiro elemento visivel do seletor (sem scroll). True se clicou."""
    try:
        loc = page.locator(selector)
        for i in range(min(loc.count(), 5)):
            el = loc.nth(i)
            try:
                if el.is_visible(timeout=300) and _click_no_scroll(page, el):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


# JS: procura o icone de fechar de um popup SEM depender de nomes de classe.
#
# Estrategia (por ordem):
#   1) Ancora na imagem do popup (.wpst-hero-image, ou a maior <img> visivel
#      que nao ocupa o ecra todo) e sobe pelos pais ate encontrar um
#      contentor que contenha controlos pequenos perto de um canto.
#   2) Fallback: qualquer elemento fixed/absolute grande (sem exigir z-index).
# Aceita elementos SEM texto no DOM (ex.: <i> com ::before), porque o "x"
# desenhado por CSS nao tem innerText.
# Devolve {x, y, how} para clicar por coordenadas, ou null.
_FIND_CLOSE_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight;
  const vis = (e) => {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' &&
           s.display !== 'none' && parseFloat(s.opacity || '1') > 0.05;
  };
  const isCornerControl = (e, box) => {
    if (!vis(e)) return false;
    const r = e.getBoundingClientRect();
    if (r.width > 56 || r.height > 56 || r.width < 5 || r.height < 5) return false;
    const txt = (e.innerText || e.getAttribute('aria-label') || e.getAttribute('title') || '').trim();
    if (txt.length > 2) return false;                 // "x", "\u00d7", "" -- nao "Regista-te"
    // nao clicar em imagens de conteudo grandes nem em links de produto
    const href = (e.closest('a') || {}).href || '';
    if (href && !/^javascript:|#$/.test(href) && e.closest('a')) return false;
    const dTop = r.top - box.top;
    const dLeft = r.left - box.left, dRight = box.right - r.right;
    return dTop < 70 && dTop > -30 && (dLeft < 70 || dRight < 70) && dLeft > -30 && dRight > -30;
  };
  const pick = (root, box) => {
    const els = [...root.querySelectorAll('*')].filter(e => isCornerControl(e, box));
    if (!els.length) return null;
    // preferir o mais proximo de um canto superior
    const score = (e) => { const r = e.getBoundingClientRect();
      return Math.min(r.left - box.left, box.right - r.right) + (r.top - box.top); };
    els.sort((a, b) => score(a) - score(b));
    const r = els[0].getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  };

  // --- 1) ancorar na imagem do popup ---
  let anchors = [...document.querySelectorAll('img.wpst-hero-image, .wpst-hero-image')].filter(vis);
  if (!anchors.length) {
    anchors = [...document.querySelectorAll('img')].filter(e => {
      if (!vis(e)) return false;
      const r = e.getBoundingClientRect();
      // grande, mas nao ecra inteiro, e razoavelmente centrada => imagem de popup
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      return r.width > vw * 0.25 && r.height > vh * 0.25 && r.width < vw * 0.95 &&
             Math.abs(cx - vw / 2) < vw * 0.15 && Math.abs(cy - vh / 2) < vh * 0.25;
    });
  }
  for (const a of anchors) {
    let node = a;
    for (let i = 0; i < 6 && node && node !== document.body; i++, node = node.parentElement) {
      const box = node.getBoundingClientRect();
      if (box.width > vw * 0.98 && box.height > vh * 0.98) break;   // overlay de ecra inteiro
      const hit = pick(node, box);
      if (hit) return { ...hit, how: 'ancora-imagem' };
    }
  }

  // --- 2) fallback: contentor fixed/absolute grande (sem exigir z-index) ---
  const popups = [...document.querySelectorAll('body *')].filter(e => {
    const s = getComputedStyle(e);
    if (s.position !== 'fixed' && s.position !== 'absolute') return false;
    if (!vis(e)) return false;
    const r = e.getBoundingClientRect();
    return r.width > vw * 0.25 && r.height > vh * 0.25 && r.width < vw * 0.98;
  });
  for (const p of popups) {
    const hit = pick(p, p.getBoundingClientRect());
    if (hit) return { ...hit, how: 'contentor-fixo' };
  }
  return null;
}
"""


def _close_by_geometry(page: Page) -> bool:
    """Fecha popup pelo icone no canto (sem depender de classes). Clica por coordenadas."""
    try:
        pos = page.evaluate(_FIND_CLOSE_JS)
        if pos:
            page.mouse.click(pos["x"], pos["y"])   # clique por coordenadas: sem scroll
            log.info(f"  (geometria: {pos.get('how')} em {pos['x']:.0f},{pos['y']:.0f})")
            return True
    except Exception:
        pass
    return False


def _close_promo_popup(page: Page, used: set, store_name: str) -> bool:
    """
    Fecha um popup promocional (ex.: Clube RP+). Tenta icones de fechar
    dentro de modais e depois glifos de texto (x). True se fechou algum.
    """
    for selector in POPUP_CLOSE_ICON_SELECTORS:
        key = f"icon:{selector}"
        if key in used:
            continue
        if _click_first_visible(page, selector):
            used.add(key)
            page.wait_for_timeout(600)
            return True

    for glyph in POPUP_CLOSE_GLYPHS:
        key = f"glyph:{glyph}"
        if key in used:
            continue
        try:
            el = page.get_by_text(glyph, exact=True).first
            if el.count() > 0 and el.is_visible(timeout=300) and _click_no_scroll(page, el):
                used.add(key)
                page.wait_for_timeout(600)
                return True
        except Exception:
            continue

    # Ultimo recurso: procurar o icone de fechar pela posicao (canto do popup)
    if "geometry" not in used and _close_by_geometry(page):
        used.add("geometry")
        page.wait_for_timeout(600)
        return True
    return False


_STILL_POPUP_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight;
  const cands = [...document.querySelectorAll('img.wpst-hero-image, body *')].filter(e => {
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || s.display === 'none' || s.visibility === 'hidden') return false;
    if (e.matches && e.matches('img.wpst-hero-image')) return true;
    return (s.position === 'fixed') && r.width > vw * 0.25 && r.height > vh * 0.25 && r.width < vw * 0.98;
  });
  if (!cands.length) return null;
  let n = cands[0];
  // subir ate um contentor razoavel para o HTML de diagnostico ter o "x" incluido
  for (let i = 0; i < 3 && n.parentElement && n.parentElement !== document.body; i++) n = n.parentElement;
  return n.outerHTML.slice(0, 6000);
}
"""


def _popup_still_open(page: Page) -> bool:
    try:
        return bool(page.evaluate(_STILL_POPUP_JS))
    except Exception:
        return False


def _dump_popup_html(page: Page, store_name: str):
    """Se o popup NAO fechou, guarda o HTML dele para diagnostico (para acertar o seletor).
    So grava ficheiro (e escreve no log) se SAVE_POPUP_DEBUG_HTML = True; caso contrario nao faz nada."""
    if not SAVE_POPUP_DEBUG_HTML:
        return
    try:
        html = page.evaluate(_STILL_POPUP_JS)
        if not html:
            return
        Path(SNAPSHOT_DIR).mkdir(exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", store_name.lower()).strip("_")
        p = Path(SNAPSHOT_DIR) / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{slug}_POPUP_NAO_FECHOU.html"
        p.write_text(html, encoding="utf-8")
        log.warning(f"[{store_name}] Popup nao fechou. HTML guardado em {p} (envia-o para ajustar o seletor)")
    except Exception as e:
        log.warning(f"[{store_name}] Nao foi possivel guardar HTML do popup: {e}")


_REMOVE_POPUP_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight;
  let removed = 0;
  // 1) o contentor do popup a partir da imagem wpst-hero-image
  document.querySelectorAll('img.wpst-hero-image').forEach(img => {
    let n = img;
    // sobe ate ao ancestral posicionado (fixed/absolute) mais proximo, sem chegar ao body
    while (n.parentElement && n.parentElement !== document.body) {
      const s = getComputedStyle(n);
      if ((s.position === 'fixed' || s.position === 'absolute') && n !== img) break;
      n = n.parentElement;
    }
    n.remove(); removed++;
  });
  // 2) overlays (fundo escurecido) de ecra inteiro, fixed, com pouco/nenhum conteudo
  document.querySelectorAll('body *').forEach(e => {
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    if (s.position !== 'fixed') return;
    if (r.width < vw * 0.95 || r.height < vh * 0.95) return;
    if (e.innerText && e.innerText.trim().length > 40) return;   // tem conteudo real: nao mexer
    const bg = s.backgroundColor || '';
    if (/rgba\(0, 0, 0, 0\.[1-9]|rgba\(0, 0, 0, 1\)|rgb\(0, 0, 0\)/.test(bg) || parseFloat(s.opacity) < 1) {
      e.remove(); removed++;
    }
  });
  document.documentElement.style.overflow = '';
  document.body.style.overflow = '';
  return removed;
}
"""


def _force_remove_popup(page: Page, store_name: str) -> bool:
    """Ultimo recurso: se nao houve forma de clicar no x, apaga popup + overlay do DOM."""
    try:
        n = page.evaluate(_REMOVE_POPUP_JS)
        if n:
            return True
    except Exception:
        pass
    return False


def dismiss_popups(page: Page, store_name: str = "", max_rounds: int = 6) -> int:
    """
    Fecha banners de cookies e popups promocionais antes de verificar o stock.

    Ordem de cada volta:
      1) fechar o POPUP promocional primeiro (o overlay dele costuma tapar o
         banner de cookies e fazia o clique em "Negar" falhar);
      2) recusar cookies;
      3) so por ultimo aceitar (lojas que nao deixam recusar, ex. MEO).
    Fechar um aviso pode revelar outro, por isso repete ate nao haver mais.

    NAO faz scroll: os cliques sao despachados sem mover a pagina, e no fim
    a pagina e reposta no topo. Nunca levanta excecao. Devolve quantos
    avisos fechou.
    """
    closed = 0
    used = set()   # seletores ja clicados -> evita cliques repetidos

    def _one_round() -> bool:
        # 1) popup promocional
        if _close_promo_popup(page, used, store_name):
            return True
        # 2) recusar, 3) aceitar (por grupos, na ordem definida)
        for group in POPUP_SELECTOR_GROUPS:
            for selector in group:
                if selector in used:
                    continue
                if _click_first_visible(page, selector):
                    used.add(selector)
                    page.wait_for_timeout(600)
                    return True
        return False

    try:
        for _ in range(max_rounds):
            if not _one_round():
                break
            closed += 1
    finally:
        # Garante que a pagina volta ao topo (a MEO ia parar ao rodape).
        try:
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass

    return closed


# ----------------------------------------------------------------------
# LOGICA DE VERIFICACAO POR LOJA
# ----------------------------------------------------------------------

def check_generic(page: Page) -> StoreResult:
    """
    Verificacao generica: procura marcadores de esgotado no texto da
    pagina e confirma se existe um botao de compra ativo.
    Usada pela MEO.
    """
    body_text = page.inner_text("body").lower()

    is_out_of_stock = any(marker in body_text for marker in GENERIC_OUT_OF_STOCK_MARKERS)

    buy_button_found = False
    try:
        buy_button = page.locator(GENERIC_BUY_BUTTON_SELECTORS).first
        if buy_button.is_visible(timeout=2000):
            buy_button_found = buy_button.is_enabled()
    except Exception:
        pass

    in_stock = (not is_out_of_stock) and buy_button_found
    detail = f"out_of_stock_marker={is_out_of_stock}, buy_button_enabled={buy_button_found}"
    return StoreResult(in_stock, detail, body_text)


def check_worten(page: Page) -> StoreResult:
    """
    Verificacao especifica da Worten.

    A Worten mistura stock proprio com marketplace (revendedores). So
    consideramos "em stock" quando:
      - nao ha marcador generico de esgotado, E
      - o botao de compra esta ativo, E
      - a pagina NAO mostra "Vendido e enviado por" / "Vendido por"
        seguido de um nome de vendedor terceiro (marketplace-seller).
    """
    body_text = page.inner_text("body").lower()

    is_out_of_stock = any(marker in body_text for marker in GENERIC_OUT_OF_STOCK_MARKERS)

    buy_button_found = False
    try:
        buy_button = page.locator(GENERIC_BUY_BUTTON_SELECTORS).first
        if buy_button.is_visible(timeout=2000):
            buy_button_found = buy_button.is_enabled()
    except Exception:
        pass

    sold_by_marketplace_seller = False
    seller_name = None
    try:
        seller_link = page.locator("a[href*='marketplace-seller']").first
        if seller_link.count() > 0:
            sold_by_marketplace_seller = True
            try:
                seller_name = seller_link.inner_text(timeout=1000).strip()
            except Exception:
                seller_name = "desconhecido"
    except Exception:
        pass

    if not sold_by_marketplace_seller:
        if ("vendido e enviado por" in body_text or "vendido por" in body_text) \
                and "worten" not in body_text.split("vendido")[-1][:60]:
            sold_by_marketplace_seller = True
            seller_name = "vendedor terceiro (deteccao por texto)"

    in_stock = (not is_out_of_stock) and buy_button_found and (not sold_by_marketplace_seller)

    detail = (
        f"out_of_stock_marker={is_out_of_stock}, buy_button_enabled={buy_button_found}, "
        f"marketplace_seller={sold_by_marketplace_seller}"
        + (f" ({seller_name})" if seller_name else "")
    )
    return StoreResult(in_stock, detail, body_text)


def _check_search_cards(page: Page, extra_card_selectors=(), buy_selectors: str = GENERIC_BUY_BUTTON_SELECTORS) -> StoreResult:
    """
    Verificacao de uma pagina de PESQUISA "ps5 pro" (Radio Popular, PcComponentes).

    A pesquisa devolve varios produtos (a consola, mas tambem comandos,
    jogos, capas... que mencionam "PS5 Pro"). Por isso avaliamos CARTAO A
    CARTAO: procuramos cartoes cujo titulo indique uma CONSOLA PS5 Pro
    (e nao um acessorio) e so consideramos stock se esse cartao especifico
    tiver botao de compra ativo e nenhum marcador de esgotado.

    Assim um "esgotado" noutro produto da lista nao esconde stock da
    consola, e um acessorio "PS5 Pro" nao da falso positivo.
    """
    body_text = page.inner_text("body").lower()

    # Palavras que indicam que o cartao NAO e a consola
    NOT_CONSOLE = (
        "comando", "dualsense", "dualsense edge", "jogo", "capa", "suporte",
        "carregador", "auscultador", "headset", "cabo", "base", "skin",
        "pelicula", "película", "cartao", "cartão", "ssd", "disco", "volante",
        "camera", "câmara", "pulse", "dock", "leitor de discos", "leitor",
    )

    # Localiza os cartoes de produto. A RP usa listas de resultados; tentamos
    # varios seletores comuns e ficamos com o primeiro que devolver cartoes.
    card_selectors = list(extra_card_selectors) + [
        "[class*='product-card']", "[class*='productCard']", "[class*='product-item']",
        "[class*='ProductCard']", "article", "li[class*='product']", "div[class*='product']",
    ]
    cards = []
    for sel in card_selectors:
        try:
            found = page.locator(sel)
            n = found.count()
            if n > 0:
                cards = [found.nth(i) for i in range(min(n, 40))]
                break
        except Exception:
            continue

    console_cards = 0
    in_stock_cards = 0
    details = []

    for card in cards:
        try:
            text = (card.inner_text(timeout=1500) or "").lower()
        except Exception:
            continue

        is_ps5_pro = ("ps5 pro" in text) or ("playstation 5 pro" in text) or ("ps5pro" in text)
        if not is_ps5_pro:
            continue

        # O titulo costuma estar nas primeiras linhas do cartao
        title = " ".join(text.split("\n")[:3])
        if any(word in title for word in NOT_CONSOLE) and "consola" not in title:
            continue  # acessorio/jogo, ignora

        console_cards += 1
        card_out_of_stock = any(m in text for m in GENERIC_OUT_OF_STOCK_MARKERS)

        buy_ok = False
        try:
            btn = card.locator(buy_selectors).first
            if btn.count() > 0 and btn.is_visible(timeout=800):
                buy_ok = btn.is_enabled()
        except Exception:
            pass

        if buy_ok and not card_out_of_stock:
            in_stock_cards += 1
            details.append(f"'{title[:50].strip()}' COM botao de compra")
        else:
            details.append(f"'{title[:50].strip()}' oos={card_out_of_stock} buy={buy_ok}")

    in_stock = in_stock_cards > 0
    detail = (
        f"cartoes_analisados={len(cards)}, cartoes_consola_ps5_pro={console_cards}, "
        f"com_stock={in_stock_cards}"
        + (f" [{'; '.join(details[:3])}]" if details else "")
    )
    return StoreResult(in_stock, detail, body_text)


def check_radio_popular(page: Page) -> StoreResult:
    """Radio Popular: pagina de pesquisa (ver _check_search_cards)."""
    return _check_search_cards(page)


# --- Ajuda para as lojas novas ---------------------------------------

BLOCK_MARKERS = (
    "just a moment", "verify you are human", "checking your browser",
    "access denied", "attention required", "captcha", "datadome",
    "pardon our interruption", "unusual traffic",
    "o nosso site não está atualmente disponível",
    "o nosso site nao esta atualmente disponivel",
    "site não está atualmente disponível",
    "em manutenção", "em manutencao",
)

LD_IN_STOCK = {"instock", "limitedavailability", "onlineonly"}
LD_OUT_OF_STOCK = {"outofstock", "soldout", "discontinued", "preorder", "backorder", "instoreonly"}


def _raise_if_blocked(page: Page, store_name: str):
    """Se a loja mostrar uma pagina anti-bot, levanta erro em vez de registar 'sem stock' falso."""
    try:
        title = (page.title() or "").lower()
        head = page.inner_text("body")[:1500].lower()
    except Exception:
        return
    hay = title + " " + head
    if any(m in hay for m in BLOCK_MARKERS) and len(head) < 1500:
        raise RuntimeError(f"{store_name}: pagina bloqueada por anti-bot ({title[:60]!r})")


def _jsonld_availability(page: Page):
    """
    Le o schema.org 'availability' do JSON-LD (Product/Offer). Devolve o valor em
    minusculas sem o URL ('instock', 'outofstock', ...) ou None se nao existir.
    Se houver varias ofertas, 'instock' ganha.
    """
    try:
        blocks = page.eval_on_selector_all(
            "script[type='application/ld+json']", "els => els.map(e => e.textContent)")
    except Exception:
        return None
    found = []

    def walk(o):
        if isinstance(o, dict):
            av = o.get("availability")
            if isinstance(av, str):
                found.append(av.rsplit("/", 1)[-1].strip().lower())
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for b in blocks:
        try:
            walk(json.loads(b))
        except Exception:
            continue
    if not found:
        return None
    return "instock" if any(f in LD_IN_STOCK for f in found) else found[0]


def _product_page_check(page: Page, store_name: str, own_seller_word: str = "", extra_oos_markers=()) -> StoreResult:
    """
    Verificacao de pagina de PRODUTO (GlobalData). Mesma logica das outras:
    sem marcador de esgotado + botao de compra ativo. Extra: se a pagina tiver
    JSON-LD com 'availability', esse valor manda sobre os marcadores de texto
    (evita falsos 'esgotado' vindos de carrosseis/rodape).
    Se own_seller_word for dado (ex.: 'worten'), so conta se o vendedor for essa loja.
    """
    _raise_if_blocked(page, store_name)
    body_text = page.inner_text("body").lower()

    ld = _jsonld_availability(page)
    if ld is not None:
        is_out_of_stock = ld not in LD_IN_STOCK
    else:
        is_out_of_stock = any(marker in body_text
                              for marker in tuple(GENERIC_OUT_OF_STOCK_MARKERS) + tuple(extra_oos_markers))

    buy_button_found = False
    button_text = None
    try:
        btn = page.locator(GENERIC_BUY_BUTTON_SELECTORS).first
        if btn.is_visible(timeout=2000):
            button_text = (btn.inner_text(timeout=1000) or "").strip().lower()
            btn_sold_out = any(m in button_text for m in ("esgotado", "sold out", "indispon"))
            buy_button_found = btn.is_enabled() and not btn_sold_out
    except Exception:
        pass

    marketplace = False
    if own_seller_word:
        sellers = re.findall(r"vendido\s+(?:e\s+(?:expedido|enviado)\s+)?por\s+([^\n]{0,60})", body_text)
        if sellers and not any(own_seller_word in s_ for s_ in sellers):
            marketplace = True

    in_stock = (not is_out_of_stock) and buy_button_found and (not marketplace)
    detail = (
        f"jsonld={ld}, out_of_stock={is_out_of_stock}, buy_button_enabled={buy_button_found}"
        + (f" (botao: '{button_text}')" if button_text else "")
        + (f", marketplace_seller={marketplace}" if own_seller_word else "")
    )
    return StoreResult(in_stock, detail, body_text)


def check_globaldata(page: Page) -> StoreResult:
    """GlobalData: pagina de produto (Salesforce Commerce Cloud). Loja propria, sem marketplace."""
    return _product_page_check(page, "GlobalData",
                               extra_oos_markers=("notifique-me quando estiver em stock",))


def check_pccomponentes(page: Page) -> StoreResult:
    """PcComponentes: pagina de PESQUISA "playstation 5 pro", avaliada cartao a cartao."""
    _raise_if_blocked(page, "PcComponentes")
    return _check_search_cards(
        page,
        extra_card_selectors=("[data-testid*='product-card' i]", "[data-testid*='product' i][class*='card' i]"),
        buy_selectors=GENERIC_BUY_BUTTON_SELECTORS + ", button[aria-label*='carrinho' i], button[aria-label*='cart' i]",
    )


def check_darty(page: Page) -> StoreResult:
    """
    Verificacao da pagina de PRODUTO da PS5 Pro na Darty (Shopify).

    Em Shopify, um produto esgotado tem o botao de compra desativado
    (disabled) ou com texto "Esgotado"/"Sold out". Consideramos "em stock"
    quando:
      - nao ha marcador de esgotado no texto da pagina, E
      - existe um botao de compra visivel e ativo.
    """
    body_text = page.inner_text("body").lower()

    is_out_of_stock = any(marker in body_text for marker in GENERIC_OUT_OF_STOCK_MARKERS)
    shopify_sold_out = "sold out" in body_text

    buy_button_found = False
    button_text = None
    try:
        # Botao de "adicionar ao carrinho" tipico do Shopify (form de produto)
        buy_btn = page.locator(
            "form[action*='/cart/add'] button[type='submit'], "
            "form[action*='/cart/add'] button[name='add'], "
            + GENERIC_BUY_BUTTON_SELECTORS
        ).first
        if buy_btn.is_visible(timeout=2000):
            button_text = (buy_btn.inner_text(timeout=1000) or "").strip().lower()
            btn_sold_out = any(m in button_text for m in ("esgotado", "sold out", "indispon"))
            buy_button_found = buy_btn.is_enabled() and not btn_sold_out
    except Exception:
        pass

    in_stock = (not is_out_of_stock) and (not shopify_sold_out) and buy_button_found

    detail = (
        f"out_of_stock_marker={is_out_of_stock}, shopify_sold_out={shopify_sold_out}, "
        f"buy_button_enabled={buy_button_found}"
        + (f" (botao: '{button_text}')" if button_text else "")
    )
    return StoreResult(in_stock, detail, body_text)


# ----------------------------------------------------------------------
# LISTA DE LOJAS A MONITORIZAR
# ----------------------------------------------------------------------

STORES = [
    Store(
        name="MEO",
        url="https://loja.meo.pt/comprar/consolas-de-jogos/sony/playstation-5-pro",
        checker=check_generic,
    ),
    Store(
        name="Worten",
        url="https://www.worten.pt/produtos/consola-ps5-pro-2-tb-branco-8155679",
        checker=check_worten,
    ),
    Store(
        name="Radio Popular",
        url="https://www.radiopopular.pt/pesquisa/consola%20ps5%20pro",
        checker=check_radio_popular,
    ),
    Store(
        name="Darty (MediaMarkt)",
        url="https://darty.pt/products/consola-playstation-5-pro-2-tb-0711719024040",
        checker=check_darty,
    ),
    Store(
        name="GlobalData",
        url="https://www.globaldata.pt/consola-sony-playstation-5-pro-edico-digital-2tb/9595472.html",
        checker=check_globaldata,
    ),
    Store(
        name="PcComponentes",
        url="https://www.pccomponentes.pt/search/?query=playstation+5+pro",
        checker=check_pccomponentes,
    ),
]

# ----------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def send_ntfy_notification(title: str, message: str, click_url: str, priority: str = "urgent"):
    """Envia uma notificacao para o telemovel via ntfy.sh"""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    data = message.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Title", title.encode("utf-8"))
    req.add_header("Priority", priority)
    req.add_header("Tags", "video_game,rotating_light")
    req.add_header("Click", click_url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log.info(f"Notificacao enviada (status {resp.status})")
    except urllib.error.URLError as e:
        log.error(f"Falha ao enviar notificacao ntfy: {e}")


def _play_sound(repeats: int):
    """Toca um alarme no PC (bloqueante -- correr numa thread)."""
    system = platform.system()
    try:
        if system == "Windows":
            import winsound
            for _ in range(repeats):
                for freq, dur in ((1000, 180), (1400, 180), (1800, 250)):
                    winsound.Beep(freq, dur)
                time.sleep(0.25)
        elif system == "Darwin":
            for _ in range(repeats):
                subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], timeout=10)
        else:
            for _ in range(repeats):
                print("\a", end="", flush=True)
                time.sleep(0.6)
    except Exception as e:
        log.exception(f"Falha ao tocar som: {e}")


def _toast_windows(title: str, message: str, click_url: str):
    """Toast nativo do Windows via winotify (pip install winotify).
    Clicar na notificacao abre a pagina da loja."""
    from winotify import Notification, audio
    toast = Notification(
        app_id="PS5 Pro Watcher",
        title=title,
        msg=message,
        duration="long",
        launch=click_url,
    )
    toast.set_audio(audio.Default, loop=False)
    toast.add_actions(label="Abrir loja", launch=click_url)
    toast.show()


def send_desktop_notification(title: str, message: str, click_url: str, repeats: int):
    """Notificacao nativa do sistema + som, sem bloquear o watcher."""
    def worker():
        if DESKTOP_NOTIFICATIONS:
            try:
                system = platform.system()
                if system == "Windows":
                    _toast_windows(title, message, click_url)
                elif system == "Darwin":
                    t = title.replace('"', "'"); m = message.replace('"', "'")
                    subprocess.run(["osascript", "-e",
                                    f'display notification "{m}" with title "{t}"'],
                                   capture_output=True, timeout=10)
                else:
                    subprocess.run(["notify-send", "-u", "critical", title, message],
                                   capture_output=True, timeout=10)
            except Exception as e:
                log.exception(f"Falha na notificacao nativa: {e}")
        if DESKTOP_SOUND:
            _play_sound(repeats)

    threading.Thread(target=worker, daemon=True).start()


def notify_all(title: str, message: str, click_url: str, priority: str = "urgent"):
    """Telemovel (ntfy) + PC (toast nativo + som)."""
    send_ntfy_notification(title, message, click_url, priority)
    repeats = SOUND_REPEATS if priority == "urgent" else SOUND_REPEATS_WARNING
    send_desktop_notification(title, message, click_url, repeats)


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


def load_state() -> dict:
    """Le o ultimo estado conhecido de cada loja (sobrevive a reinicios)."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    except Exception as e:
        log.warning(f"Nao foi possivel ler {STATE_FILE}: {e}")
        return {}


def save_state(state: dict):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        Path(tmp).replace(STATE_FILE)
    except Exception as e:
        log.warning(f"Nao foi possivel gravar {STATE_FILE}: {e}")


def save_snapshot(store_name: str, when: datetime, label: str, result: StoreResult) -> str:
    """Grava o texto da pagina (.txt) + foto (.png) da verificacao. Devolve o caminho do .txt."""
    try:
        Path(SNAPSHOT_DIR).mkdir(exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", store_name.lower()).strip("_")
        path = Path(SNAPSHOT_DIR) / f"{when:%Y-%m-%d_%H-%M-%S}_{slug}_{label}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Loja: {store_name}\n")
            f.write(f"Hora: {when:%Y-%m-%d %H:%M:%S}\n")
            f.write(f"Estado: {label}\n")
            f.write(f"Detalhe: {result.detail}\n")
            f.write("-" * 60 + "\n")
            f.write(result.page_text[:SNAPSHOT_MAX_CHARS])
        if result.screenshot:
            try:
                path.with_suffix(".png").write_bytes(result.screenshot)
            except Exception as e:
                log.warning(f"[{store_name}] Nao foi possivel gravar a foto: {e}")
        return str(path)
    except Exception as e:
        log.warning(f"[{store_name}] Nao foi possivel gravar snapshot: {e}")
        return ""


def record_state_change(store: Store, result: StoreResult, state: dict):
    """
    Compara com o ultimo estado conhecido da loja. Se mudou, escreve uma
    linha destacada no log (com a hora exata e, se voltou a esgotar, a
    duracao do stock) e guarda um snapshot. Atualiza sempre 'last_check'.
    """
    now = datetime.now()
    now_iso = now.isoformat(timespec="seconds")
    label = "COM_STOCK" if result.in_stock else "SEM_STOCK"
    prev = state.get(store.name)

    if prev is None:
        # Primeira vez que vemos esta loja: regista o estado inicial
        log.info(f"[{store.name}] >>> ESTADO INICIAL: {label} as {now:%Y-%m-%d %H:%M:%S}")
        snap = save_snapshot(store.name, now, label, result)
        state[store.name] = {
            "in_stock": result.in_stock, "since": now_iso, "last_check": now_iso,
            "last_snapshot": snap,
        }
        save_state(state)
        return

    prev["last_check"] = now_iso

    if prev["in_stock"] != result.in_stock:
        since = datetime.fromisoformat(prev["since"])
        held = _fmt_duration((now - since).total_seconds())
        snap = save_snapshot(store.name, now, label, result)

        if result.in_stock:
            log.warning(
                f"[{store.name}] >>> MUDANCA DE ESTADO: SEM_STOCK -> COM_STOCK "
                f"as {now:%Y-%m-%d %H:%M:%S} (estava sem stock desde {since:%H:%M:%S}, {held}). "
                f"Snapshot: {snap}"
            )
        else:
            log.warning(
                f"[{store.name}] >>> MUDANCA DE ESTADO: COM_STOCK -> SEM_STOCK "
                f"as {now:%Y-%m-%d %H:%M:%S} (esteve com stock de {since:%H:%M:%S} "
                f"a {now:%H:%M:%S} = {held}). Snapshot: {snap}"
            )
        prev.update({
            "in_stock": result.in_stock, "since": now_iso,
            "previous_snapshot": prev.get("last_snapshot", ""),
            "last_snapshot": snap,
        })
    save_state(state)


def check_store(playwright, store: Store) -> StoreResult:
    """Abre a pagina da loja num Chrome headless e corre o checker especifico."""
    browser = playwright.chromium.launch(
        headless=True,
        channel=BROWSER_CHANNEL,
        args=["--disable-blink-features=AutomationControlled"],
    )
    try:
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="pt-PT",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()

        # "domcontentloaded" em vez de "networkidle": varias lojas (Worten,
        # Darty) tem scripts de analytics/chat que nunca "acalmam" a rede,
        # o que fazia o networkidle disparar timeout sempre. Com
        # domcontentloaded + uma espera fixa a seguir, o conteudo dinamico
        # (React/Shopify) tem tempo de renderizar na mesma.
        last_error = None
        for attempt in (1, 2):
            try:
                page.goto(store.url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3500)
                # Fecha cookies / popups ANTES de verificar (e antes do
                # screenshot, para a foto mostrar a pagina limpa).
                dismiss_popups(page, store.name)
                # Alguns popups aparecem tarde (injetados por JS). Se ainda
                # ha um popup visivel, espera e tenta outra vez; se mesmo
                # assim nao fechar, guarda o HTML para diagnostico.
                if _popup_still_open(page):
                    page.wait_for_timeout(2500)
                    dismiss_popups(page, store.name)
                    if _popup_still_open(page):
                        _dump_popup_html(page, store.name)   # 1o guarda o HTML (diagnostico)
                        _force_remove_popup(page, store.name)  # 2o apaga-o do DOM
                result = store.checker(page)
                if SCREENSHOT_ON_CHANGE:
                    # Tirada aqui porque o browser fecha logo a seguir. Fica
                    # em memoria; so e gravada se houver mudanca de estado.
                    try:
                        result.screenshot = page.screenshot(full_page=SCREENSHOT_FULL_PAGE)
                    except Exception as e:
                        log.warning(f"[{store.name}] Nao foi possivel tirar screenshot: {e}")
                return result
            except Exception as e:
                last_error = e
                if attempt == 1:
                    log.warning(f"[{store.name}] Falhou 1a tentativa ({e}), a repetir...")
                    time.sleep(3)
        raise last_error
    finally:
        browser.close()


def main():
    if "MUDA-ISTO" in NTFY_TOPIC or "INSERE-AQUI" in NTFY_TOPIC:
        log.error(
            "Configura primeiro o NTFY_TOPIC no topo do script para um "
            "nome unico e secreto antes de correr o watcher."
        )
        sys.exit(1)

    log.info("A iniciar monitor de stock da PS5 Pro (multiplas lojas)...")
    for s in STORES:
        log.info(f"  - {s.name}: {s.url}")
    log.info(f"Notificacoes via: https://ntfy.sh/{NTFY_TOPIC} + toast/som no PC")

    consecutive_errors = 0
    state = load_state()

    with sync_playwright() as playwright:
        while True:
            for store in STORES:
                try:
                    result = check_store(playwright, store)
                    consecutive_errors = 0
                    record_state_change(store, result, state)

                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    if result.in_stock:
                        log.info(f"[{store.name}] STOCK DISPONIVEL! ({result.detail})")

                        now = time.time()
                        if now - store.last_notified_at > RENOTIFY_COOLDOWN_SECONDS:
                            notify_all(
                                title=f"🎮 PS5 Pro EM STOCK na {store.name}!",
                                message=(
                                    f"Detectado stock as {timestamp}.\n"
                                    f"Vai comprar ja: {store.url}"
                                ),
                                click_url=store.url,
                            )
                            store.last_notified_at = now
                        else:
                            log.info(f"[{store.name}] Ja notificado recentemente, a aguardar cooldown.")
                    else:
                        log.info(f"[{store.name}] Sem stock. ({result.detail})")

                except Exception as e:
                    consecutive_errors += 1
                    log.error(f"[{store.name}] Erro na verificacao: {e}")

                    if consecutive_errors == 5:
                        notify_all(
                            title="⚠️ PS5 Pro Watcher com problemas",
                            message=(
                                f"5 erros seguidos a verificar as paginas. "
                                f"Verifica o log: {LOG_FILE}"
                            ),
                            click_url=store.url,
                            priority="high",
                        )

                time.sleep(random.uniform(3, 8))

            wait_time = random.uniform(CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX)
            log.info(f"Proxima ronda de verificacoes em {wait_time:.0f} segundos...")
            time.sleep(wait_time)


if __name__ == "__main__":
    main()
