# Monitor de Stock — PlayStation 5 Pro 

Verifica periodicamente a página da PS5 Pro em **6 lojas portuguesas** usando o Chrome (em segundo plano, invisível) e avisa-te assim que detetar stock em qualquer uma delas: **notificação no telemóvel (ntfy) + notificação nativa e alarme sonoro no PC**.

**Principais Lojas monitorizadas:**

- MEO
- Worten *(só notifica quando for vendido e enviado pela própria Worten — ignora ofertas de revendedores/marketplace)*
- Rádio Popular
- Darty (MediaMarkt)
- GlobalData
- PcComponentes

Cada notificação diz de que loja veio o stock e tem um link direto para lá.

## 🟢 GUIA PARA QUEM NÃO PERCEBE NADA DE INFORMÁTICA (Windows)

Segue os passos pela ordem. Só precisas de **um PC com Windows**, ligado à internet, e de **um telemóvel** para receber os avisos.

### O que é isto e o que vai fazer?

É um pequeno programa que **fica a espreitar sozinho** as páginas da PS5 Pro nas lojas MEO, Worten, Rádio Popular, Darty (MediaMarkt), GlobalData e PcComponentes. Assim que uma loja tiver stock, **o teu telemóvel apita** e o PC também (aviso no ecrã + som).

Funciona **em segundo plano**: não abre janelas, não vês nada a acontecer e podes continuar a usar o PC normalmente (ver vídeos, trabalhar, etc.). O programa só "acorda" para avisar quando há stock.

**Importante:** o PC tem de estar **ligado, com internet e sem estar em suspensão** para o programa funcionar. Se desligares ou suspenderes o PC, ele deixa de verificar.

### Passo 1 — Instalar o Python (o "motor" que faz o programa andar)

1.  Vai a **<https://www.python.org/downloads/>** e clica no botão amarelo **Download Python**.
2.  Abre o ficheiro que descarregou.
3.  ⚠️ **MUITO IMPORTANTE:** no primeiro ecrã, **marca a caixinha em baixo** onde diz **"Add python.exe to PATH"**. Se te esqueceres disto, nada funciona.
4.  Clica em **Install Now** e espera. No fim clica em **Close**.

### Passo 2 — Guardar os ficheiros numa pasta

1.  Nesta página do GitHub, clica no botão verde **Code** → **Download ZIP**. Depois clica com o botão direito no ficheiro descarregado → **Extrair tudo…** → **Extrair**.
2.  Move a pasta que apareceu para um sítio onde a vás encontrar facilmente (por exemplo, o Ambiente de Trabalho). **Não a apagues nem mudes de sítio depois de tudo configurado.**
3.  Não corras nada de dentro do .zip: tens de o extrair primeiro.

### Passo 3 — Instalar as peças de que o programa precisa (só uma vez)

1.  Abre a pasta que extraíste (a que tem o `meo_ps5pro_watcher.py`).

2.  Clica na **barra de endereço** no topo da janela (onde aparece o caminho da pasta), escreve `cmd` e carrega em **Enter**. Abre uma janela preta — é normal.

3.  Copia esta linha, cola na janela preta (botão direito do rato cola) e carrega em Enter:

    ```bash
    pip install playwright winotify
    ```

4.  Quando acabar, faz o mesmo com esta:

    ```bash
    python -m playwright install chromium
    ```

    Demora alguns minutos e descarrega uns 150 MB. Espera até voltares a ver o cursor a piscar.

5.  Podes fechar a janela preta. Não feches ainda se vires que ainda está a trabalhar.

### Passo 4 — Receber avisos no telemóvel (ntfy)

1.  Instala no telemóvel a app gratuita **ntfy** ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iPhone](https://apps.apple.com/us/app/ntfy/id1625396347)).

2.  Na app, carrega no **+** para subscrever um "tópico". Inventa um **nome único e difícil de adivinhar**, por exemplo `ps5-joao-k93x72` (sem espaços, sem acentos). Qualquer pessoa que souber este nome consegue ver os teus avisos, por isso **não uses** nomes óbvios como `ps5`.

3.  No PC, clica com o botão direito no ficheiro `meo_ps5pro_watcher.py` → **Abrir com** → **Bloco de Notas**.

4.  Perto do início, procura esta linha:

    ```python
    NTFY_TOPIC = "INSERE-AQUI-O-TOPICO"
    ```


    Apaga só o texto **entre as aspas** e escreve o nome que inventaste no ponto 2. **Mantém as aspas.** Fica assim:

    ```python
    NTFY_TOPIC = "ps5-joao-k93x72"
    ```


5.  **Ficheiro → Guardar** e fecha o Bloco de Notas.

### Passo 5 — Fazer um teste rápido (recomendado)

1.  Abre outra vez a janela preta como no Passo 3 (escrever `cmd` na barra de endereço da pasta).
2.  Escreve `python meo_ps5pro_watcher.py` e carrega em Enter.
3.  Se aparecerem mensagens a dizer "A iniciar monitor de stock…" e o nome das lojas, **está a funcionar**. Se aparecer um erro vermelho, vê a secção "Problemas comuns" mais abaixo.
4.  Para parar o teste, carrega em **Ctrl + C** ou fecha a janela preta.

### Passo 6 — Pô-lo a trabalhar em segundo plano

1.  Na pasta, faz **duplo clique** no ficheiro **`iniciar_watcher.vbs`**.
2.  **Não vai aparecer nada.** É isso mesmo que se quer: o programa ficou a correr escondido.
3.  Para confirmares que está vivo, abre o ficheiro `meo_ps5pro_watcher.log` (fica na mesma pasta, abre com o Bloco de Notas). Devem aparecer linhas novas com a data e hora de há poucos minutos.

⚠️ Faz duplo clique **só uma vez**. Se o fizeres duas vezes ficam dois programas a correr e recebes avisos repetidos.

### Como parar o programa

1.  Carrega em **Ctrl + Shift + Esc** (abre o Gestor de Tarefas).
2.  Se só vires uma lista curta, clica em **Mais detalhes**.
3.  Separador **Detalhes**, procura **pythonw.exe**, clica com o botão direito → **Terminar tarefa**.

### Como fazer com que arranque sozinho quando ligas o PC (opcional)

1.  Carrega em **Windows + R**, escreve `shell:startup` e carrega em Enter. Abre-se uma pasta.
2.  Volta à pasta do programa, clica com o **botão direito** em `iniciar_watcher.vbs` → **Mostrar mais opções** → **Enviar para** → **Ambiente de trabalho (criar atalho)**.
3.  Arrasta esse atalho para a pasta que abriste no ponto 1.

A partir daí, o programa arranca sozinho sempre que iniciares sessão no Windows.

### O que vais ver quando houver stock

- No telemóvel: uma notificação urgente da app ntfy, com a loja e um link direto.
- No PC: uma notificação do Windows (clica nela para abrir a loja) e um alarme sonoro.
- Se as notificações do PC não aparecerem, verifica se o Windows não está em modo **Não incomodar / Assistente de Foco**.

### Problemas comuns

| Problema                                                       | O que fazer                                                                                                                                               |
|----------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| Aparece *"python não é reconhecido como um comando…"*          | O Python foi instalado sem a caixa **"Add python.exe to PATH"**. Volta a instalar e marca essa caixa.                                                     |
| Dei duplo clique no `.vbs` e não acontece nada nem aparece log | Corre o programa como no **Passo 5** para veres a mensagem de erro. Normalmente falhou algum passo de instalação ou apagaste uma aspa ao editar o tópico. |
| O telemóvel não recebe nada                                    | Confirma que o nome do tópico é **exatamente igual** na app e no ficheiro (maiúsculas/minúsculas contam).                                                 |
| Avisos repetidos                                               | Provavelmente há dois programas a correr. Fecha os `pythonw.exe` no Gestor de Tarefas e abre o `.vbs` só uma vez.                                         |
| Movi ou apaguei a pasta                                        | Tens de a manter no mesmo sítio, ou repetir o Passo 6 a partir da nova localização.                                                                       |

**Mac ou Linux?** O ficheiro `.vbs` só funciona em Windows. Usa a secção técnica abaixo (passos 1 a 4).

------------------------------------------------------------------------

# 🔧 Documentação técnica (para quem já sabe usar Python)

## 1. Instalar (só precisas de fazer isto uma vez)

Abre uma consola (cmd / PowerShell / terminal) e corre:

```bash
pip install playwright winotify
python -m playwright install chromium
```


(`winotify` é a biblioteca que mostra a notificação nativa no Windows.)

Isto instala a biblioteca Python e uma cópia própria do Chromium que o script vai controlar (não mexe no teu Chrome normal, é uma instância à parte).

## 2. Configurar o ntfy.sh (notificações no telemóvel)

1.  Instala a app **ntfy** ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/us/app/ntfy/id1625396347)).
2.  Na app, adiciona um "topic" (tópico) com um **nome único e secreto** — por exemplo `ps5pro-stock-a8x92k`. Qualquer pessoa que souber este nome consegue ver as tuas notificações, por isso não uses algo óbvio como `ps5pro-stock`.
3.  Abre o ficheiro `meo_ps5pro_watcher.py` e edita a linha:
    ```python
    NTFY_TOPIC = "INSERE-AQUI-O-TOPICO"
    ```


    Substitui pelo nome que escolheste no ponto 2.

## 2b. Notificação nativa + som no PC (já vem ligado)

Precisa do `winotify` (`pip install winotify`, já incluído no passo 1). Quando há stock:

- aparece um **toast nativo do Windows** (clica nele para abrir a loja);
- o PC toca um **alarme sonoro** (8 repetições, configurável).

Ajusta no topo do script:

```python
DESKTOP_NOTIFICATIONS = True   # False para desligar o toast
DESKTOP_SOUND = True           # False para desligar o som
SOUND_REPEATS = 8              # nº de repetições do alarme
```


Se o toast não aparecer, verifica o **Assistente de Foco / Não incomodar** do Windows (Definições \> Sistema \> Notificações). Os erros ficam no log. No Mac usa notificações + `afplay`; no Linux usa `notify-send`.

## 3. Correr o script

```bash
python meo_ps5pro_watcher.py
```


Deixa a consola aberta (ou corre em segundo plano — ver secção abaixo). O script:

- Verifica cada ronda de lojas a cada 45–90 segundos (intervalo aleatório, para não parecer um robô)
- Regista tudo em `meo_ps5pro_watcher.log`
- Assim que detetar stock, envia-te logo uma notificação urgente
- Não volta a notificar-te nos 15 minutos seguintes (evita spam)
- Se falhar 5 vezes seguidas a verificar, avisa-te que algo pode estar mal

## 4. Correr sempre em segundo plano (opcional, recomendado)

### Windows

Cria um ficheiro `.bat` com:

```bat
@echo off
cd /d "%~dp0"
python meo_ps5pro_watcher.py
```


E usa o **Agendador de Tarefas** do Windows para o correr ao iniciar sessão, ou simplesmente deixa a janela minimizada.

### Mac/Linux

```bash
nohup python3 meo_ps5pro_watcher.py &
```


Isto continua a correr mesmo que feches o terminal.

## Avisos de cookies e popups (fechados automaticamente)

Antes de cada verificacao o script **fecha sozinho** os avisos que tapam a pagina:

| Loja          | O que fecha                                             |
|---------------|---------------------------------------------------------|
| Darty         | "Continuar sem aceitar" (cookies)                       |
| MEO           | "Concordo" (so oferece esta opcao ou "Mais opcoes")     |
| Worten        | "Rejeitar cookies"                                      |
| Radio Popular | popup Clube RP+ (icone x) e banner de cookies ("Negar") |

Prefere sempre **recusar** cookies; so aceita quando a loja nao deixa recusar (caso do MEO). O fecho de avisos e silencioso: nao escreve nada no log.

**Como funciona (versao corrigida):**

- **Popup primeiro, cookies depois.** O popup promocional (Clube RP+) tem um overlay que tapa o banner de cookies; se se tentasse recusar cookies antes, o clique falhava. Agora fecha-se sempre o popup em primeiro lugar.
- **Encontra o "x" mesmo sem texto.** Procura-o por seletores (classe/id de modal/popup) e, se falhar, **pela posicao**: o botao pequeno no canto de um popup grande. Assim funciona mesmo que a loja mude os nomes das classes.
- **Nao faz scroll.** Os cliques sao feitos sem mover a pagina, e no fim ela e reposta no topo. (Antes, na MEO, o banner de cookies esta no fim do documento e o clique arrastava a pagina para o rodape.)

**A deteccao de stock funciona mesmo com avisos abertos:** um popup e so uma camada visual por cima; o texto e os botoes da pagina continuam la por baixo. Fechar os avisos serve sobretudo para a foto (screenshot) mostrar a pagina limpa.

**Sem ficheiros HTML de diagnostico.** Se um popup nao fechar por clique, o script remove-o do DOM e segue em frente, sem escrever no log nem criar ficheiros `*_POPUP_NAO_FECHOU.html`. Para os reativar (so para diagnosticar um seletor), poe `SAVE_POPUP_DEBUG_HTML = True` no topo do script (isto tambem volta a registar no log).

Se uma loja mudar o texto dos botoes e os avisos voltarem a aparecer, basta acrescentar o novo seletor em `POPUP_SELECTOR_GROUPS` (cookies) ou `POPUP_CLOSE_ICON_SELECTORS` (icones x), no topo do script.

## Notas importantes

- **Intervalo**: cada ronda passa pelas 6 lojas com pausas curtas entre cada uma, e depois espera 45–90 segundos (aleatório) antes da ronda seguinte. Isto significa que, na prática, cada loja individual acaba por ser verificada a um ritmo um pouco mais espaçado do que 45–90s, o que é bom — reduz ainda mais o risco de bloqueio por loja.
- **Worten**: o script só notifica quando o produto é vendido **pela própria Worten**. Se aparecer stock só de um revendedor do marketplace (normalmente com preço muito mais alto), não recebes notificação — é o comportamento pretendido.
- **Darty**: o script aponta diretamente para a página de produto da PS5 Pro 2 TB (`darty.pt/products/consola-playstation-5-pro-2-tb-0711719024040`) e considera "em stock" quando desaparece o marcador "Esgotado" e o botão "Adicionar ao carrinho" fica ativo.
- **Rádio Popular**: o script aponta para a página de **pesquisa** (`radiopopular.pt/pesquisa/consola%20ps5%20pro`). Como a pesquisa também devolve comandos, jogos e capas que mencionam "PS5 Pro", o script analisa **cartão a cartão**: só conta como stock se houver um cartão de **consola** PS5 Pro (ignora acessórios) com botão de compra ativo e sem "esgotado". Um acessório com stock ou uma consola esgotada ao lado **não** dão falso alarme.
- **Se alguma loja mudar o design da página**, os marcadores de "esgotado" podem deixar de bater certo. Se reparares que o script para de detetar corretamente para alguma loja específica, abre uma *issue* neste repositório ou ajusta os seletores dessa loja no script.
- **Isto não garante 100%** que nunca serás bloqueado — depende da proteção que cada site usar. Se começares a ver muitos erros seguidos no log para uma loja em particular, considera aumentar o intervalo ou pausar essa loja por umas horas.

## Histórico de mudanças de estado (quando apareceu / desapareceu stock)

Sempre que uma loja **muda de estado** (sem stock → com stock, ou o contrário), o script regista a **hora exata** no `meo_ps5pro_watcher.log`, numa linha fácil de encontrar, e guarda um **snapshot** da página nessa altura.

Exemplo no log:

```text
[WARNING] [Darty (MediaMarkt)] >>> MUDANCA DE ESTADO: SEM_STOCK -> COM_STOCK as 2026-09-28 14:03:00 (estava sem stock desde 14:00:00, 3m 00s). Snapshot: snapshots/...
[WARNING] [Darty (MediaMarkt)] >>> MUDANCA DE ESTADO: COM_STOCK -> SEM_STOCK as 2026-09-28 14:05:00 (esteve com stock de 14:03:00 a 14:05:00 = 2m 00s). Snapshot: snapshots/...
```

Para veres só as mudanças (sem o resto do ruído), pesquisa por `MUDANCA DE ESTADO`:

```bash
# Windows (PowerShell)
Select-String "MUDANCA DE ESTADO" meo_ps5pro_watcher.log
# Mac/Linux
grep "MUDANCA DE ESTADO" meo_ps5pro_watcher.log
```


Ficheiros criados (na mesma pasta do script):

- `snapshots/` — por cada mudança, **dois ficheiros com o mesmo nome**: um `.png` (**foto da página** nesse momento: preço, botão, vendedor) e um `.txt` (hora, detalhe da verificação e texto da página). Assim comparas o "antes" (`SEM_STOCK`) com o "depois" (`COM_STOCK`), e tens prova do que a loja mostrava (útil se o preço estiver errado ou o vendedor for terceiro).
- `estado_lojas.json` — o último estado de cada loja. Serve para o histórico **sobreviver a reinícios** do script/PC. Se o apagares, a próxima verificação conta como "estado inicial".

Notas:

- **A duração tem a precisão da cadência de verificação.** O script só vê a página a cada 45–90 s (por loja, mais espaçado), por isso "2m 00s" significa "entre a 1.ª e a última verificação em que vimos stock". Uma janela de stock mais curta do que o intervalo pode passar despercebida.
- **A foto só é tirada nas mudanças de estado**, não em todas as verificações (senão enchia o disco). Em cada verificação tira-se em memória e só se grava se a loja mudou. Cada foto ocupa ~50–300 KB.
- Configurável no topo do script: `SCREENSHOT_ON_CHANGE = False` desliga as fotos; `SCREENSHOT_FULL_PAGE = True` fotografa a página inteira (mais pesado) em vez de só a parte visível.
- Se as mudanças forem muitas (página a oscilar), a pasta `snapshots/` cresce. Podes apagá-la à vontade; só o `estado_lojas.json` é necessário para manter a memória do último estado.

## Se o script "não faz nada"

O `iniciar_watcher.vbs` usa `pythonw.exe`, que **não mostra janela nem erros**. Se editares o script e ele deixar de funcionar (por exemplo, por uma aspa ou vírgula em falta), não vês nada. Para ver o erro, corre numa consola:

```bash
python meo_ps5pro_watcher.py
```


Se houver um erro de sintaxe aparece logo ali com o número da linha.
