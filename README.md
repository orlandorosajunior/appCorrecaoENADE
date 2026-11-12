# Corretor de Gabarito — Simulado ENADE (ADS)

App em Streamlit, com **banco de dados local (SQLite)** e **login
obrigatório**, para:

- **restringir o acesso ao app** com login (usuário/senha) — ninguém vê ou
  edita dados sem entrar antes;
- cadastrar **turmas** e **alunos** uma vez só, e depois apenas selecioná-los
  (sem redigitar) em cada correção;
- cadastrar **simulados** e definir o **gabarito oficial** de cada um
  (manualmente ou fotografando uma folha já preenchida com as respostas
  corretas);
- opcionalmente, definir uma **rubrica para a questão discursiva (32)** e
  pedir uma **avaliação sugerida por IA** (via API do Google Gemini, com
  visão) a partir da foto da resposta manuscrita do aluno;
- **corrigir a prova de cada aluno**, fotografando/escaneando a folha
  preenchida, com leitura óptica (OMR) calibrada para o template oficial do
  Cartão-Resposta, e opcionalmente registrando o **horário de início e fim**
  da prova;
- calcular automaticamente uma **nota na escala 0-1000** (estilo ENEM —
  ver observação importante mais abaixo sobre o que isso significa e o que
  NÃO significa);
- manter um **histórico** de todas as correções, com filtros, médias,
  percentual de acerto por questão e exportação CSV;
- consultar um **dashboard** com indicadores estatísticos (média, mediana,
  desvio padrão, distribuição das notas) por turma e por aluno, e a
  correlação entre tempo de prova e nota.

## Como rodar

```bash
pip install -r requirements.txt
streamlit run app.py
```

Isso abre a página inicial; use o menu à esquerda para navegar entre
**Simulados e Gabaritos**, **Corrigir Prova** e **Histórico**.

Para usar a câmera do **celular**, rode com
`streamlit run app.py --server.address 0.0.0.0` e acesse pelo IP do
computador na rede local (ou publique num serviço como Streamlit Community
Cloud) — navegadores só liberam câmera em `localhost` ou HTTPS.

## Login

Toda página do app (inclusive a inicial) exige estar logado — sem isso,
não é possível ver nem editar nenhum dado.

- **Primeiro acesso**: como ainda não existe nenhum usuário, a tela mostra
  um formulário para criar a primeira conta (usuário + senha, mínimo de 6
  caracteres). Essa conta já entra com acesso completo ao sistema.
- **Acessos seguintes**: tela de login normal (usuário + senha).
- **Sair**: aparece um botão "Sair" na barra lateral sempre que você está
  logado.
- **Gerenciar contas**: em *Configurações* → seção "Usuários", dá para
  criar novas contas (ex.: para um TA ou outro professor usarem o mesmo
  app), trocar sua própria senha, e excluir contas (não deixa excluir a
  última conta restante).

Pontos importantes sobre esse login:

- **Senhas nunca são guardadas em texto puro** — usa PBKDF2-HMAC-SHA256
  (200 mil iterações) com um salt aleatório por usuário, usando só a
  biblioteca padrão do Python (`hashlib`), sem depender de serviço externo.
- **É um controle de acesso único, não um sistema de permissões por
  papel**: qualquer conta logada vê e edita todos os simulados, turmas,
  alunos e correções — não existe usuário "somente leitura" nem
  segregação de dados entre professores diferentes que usem a mesma
  instalação. Serve para manter pessoas não autorizadas fora do app, não
  para dividir o acesso dentro de uma equipe.
- Se você esquecer a senha e não houver outra conta para redefini-la, o
  jeito mais simples de recomeçar é apagar a tabela `usuarios` do banco
  (`data/gabarito_app.db`) — isso NÃO apaga simulados/correções, só as
  contas — e criar uma conta nova no próximo acesso.

## Fluxo de uso

0. **(Opcional, mas recomendado) Configurar** (página *Configurações*):
   salve sua chave de API do Gemini e os parâmetros padrão de leitura —
   assim você não precisa digitar a chave toda vez que for avaliar uma
   questão discursiva. Tem um botão "Testar chave" para confirmar que
   está tudo certo antes de usar em uma correção de verdade.
1. **Cadastrar turmas e alunos** (página *Turmas e Alunos*): cadastre suas
   turmas e os alunos de cada uma. Isso é feito uma vez só — depois é só
   selecionar na hora de corrigir (também dá para cadastrar um aluno novo
   direto na tela de correção, sem precisar trocar de página).
2. **Cadastrar o simulado** (página *Simulados e Gabaritos*): dê um nome
   (ex.: "Simulado ENADE 2026.2").
3. **Definir o gabarito** desse simulado, de duas formas:
   - **Manual**: uma tabela com uma linha por questão e um menu suspenso
     (A–E) para marcar a alternativa correta.
   - **Via foto**: fotografe/envie uma folha já preenchida com as respostas
     certas — o sistema lê automaticamente e mostra uma tabela editável
     para você revisar/corrigir antes de salvar.
4. **Corrigir provas** (página *Corrigir Prova*): escolha o simulado, a
   turma e o aluno (ou cadastre um novo ali mesmo), opcionalmente registre
   o horário de início/fim da prova, e envie a foto da folha preenchida.
   O sistema mostra a imagem anotada (verde = acerto, vermelho = erro,
   laranja = resposta certa não marcada) e uma **tabela editável** com a
   leitura, para você corrigir qualquer marcação lida errado antes de
   salvar. A nota na escala 0-1000 é calculada automaticamente. Ao salvar,
   a correção entra no histórico.
5. **Consultar o histórico** (página *Histórico*): filtre por simulado,
   turma ou aluno; veja nota média, média por turma e o percentual de
   acerto por questão (ajuda a identificar questões mais difíceis);
   exporte em CSV; exclua correções lançadas por engano.
6. **Recorrigir, se precisar** (página *Recorrigir*): reabra qualquer
   correção salva para revisar ou corrigir qualquer campo.
7. **Consultar o dashboard** (página *Dashboard*): média, mediana, desvio
   padrão e distribuição das notas por turma; comparativos entre turmas;
   evolução de um aluno específico ao longo de vários simulados; e a
   correlação entre tempo de prova e nota (quando o horário foi
   registrado).
8. **Exportar dados** (página *Exportar*): baixe as correções filtradas
   por simulado/turma/aluno em CSV ou Excel, ou gere um boletim (aluno x
   simulado) de uma turma inteira.

## Recorrigir

A página *Recorrigir* reabre qualquer correção já salva com **todos os
campos editáveis**:

- **Aluno e turma** — pode reatribuir se selecionou o aluno errado.
- **Horário de início/fim** — corrige ou adiciona o horário, recalculando
  o tempo de prova.
- **Respostas objetivas** — a tabela já vem preenchida com o que foi
  salvo; edite direto, ou (num expansor) envie uma foto nova e reprocesse
  do zero se quiser reler o cartão inteiro.
- **Questão discursiva** — mostra a foto já anexada (com opção de trocar),
  a **transcrição que a IA fez** da resposta do aluno, a **justificativa
  de cada item** e o **resumo** que a IA escreveu da primeira vez — tudo
  isso pré-carregado, sem precisar clicar em "Avaliar" de novo. Isso é
  pensado especialmente para você reler o que a IA disse antes de montar
  o feedback para o aluno, e corrigir a pontuação se necessário.

A nota (objetiva, 0-1000) é recalculada automaticamente a partir dos
valores editados, e só é gravada quando você clica em "Salvar alterações".

## Turmas e Alunos

Cadastre turmas (só um nome) e alunos (nome + turma, matrícula opcional)
na página *Turmas e Alunos* — manualmente ou **importando de uma
planilha**. Excluir uma turma **não apaga os alunos** dela — eles ficam
sem turma associada, e dá para reatribuí-los depois. Excluir um aluno não
apaga correções já salvas com o nome dele (o histórico continua mostrando
o nome, só perde o vínculo com o cadastro).

Na página *Corrigir Prova*, escolha primeiro a turma e depois o aluno
(a lista de alunos é filtrada pela turma escolhida). Se o aluno ainda não
estiver cadastrado, um expansor logo abaixo permite cadastrá-lo e
selecioná-lo na hora, sem sair da tela.

### Importar alunos de uma planilha

Na aba *Alunos*, expansor "Importar alunos de uma planilha de turma":

1. Envie o arquivo — aceita `.xlsx`, `.csv` e `.xls` **mesmo quando esse
   `.xls` é, na verdade, um HTML** (muito comum: sistemas acadêmicos
   "exportam para Excel" só trocando a extensão, sem converter o
   conteúdo — o app detecta e lê esse caso automaticamente).
2. Escolha **qual coluna é o nome do aluno** e, opcionalmente, **qual é a
   matrícula** — o app tenta adivinhar (procura colunas chamadas "Aluno",
   "Nome", "Matrícula", "RA" etc.), mas funciona com qualquer nome de
   coluna, você só confirma ou troca.
3. Escolha a turma de destino (uma já cadastrada, ou crie uma nova — o
   nome do arquivo entra como sugestão, ex.: `4ADS.xls` → turma "4ADS").
4. **Revise antes de confirmar**: a tabela extraída fica editável, com uma
   caixa "Incluir" por linha — desmarque quem não deve entrar (cabeçalhos
   repetidos, linhas em branco etc. já são filtrados automaticamente, mas
   vale conferir).
5. Clique em "Importar". Reimportar a mesma planilha depois não duplica
   ninguém: alunos já cadastrados (por matrícula, ou por nome dentro da
   mesma turma) são reconhecidos — e se a matrícula bater mas a turma
   informada for outra, o aluno é **movido** para a nova turma em vez de
   duplicado (útil para corrigir um cadastro ou uma turma que mudou).

## Nota na escala 0-1000 (estilo ENEM)

**Leia isto antes de usar esse número com os alunos.** A nota real do
ENEM/ENADE é calculada por **TRI (Teoria de Resposta ao Item)** — um
modelo estatístico calibrado com a resposta de centenas de milhares de
participantes, que leva em conta a dificuldade e o poder de discriminação
de cada questão. Duas provas com o mesmo número de acertos podem ter notas
TRI bem diferentes, dependendo de *quais* questões foram acertadas. Esse
cálculo depende de uma base populacional gigantesca e não é algo que dá
para reproduzir a partir dos dados de uma única turma.

O que este app calcula é uma **conversão proporcional simples (linear)**
para a escala 0-1000, com **peso configurável** para a questão discursiva
(em *Configurações* → "Peso da discursiva na nota final"):

```
peso_discursiva = quantos dos 1000 pontos a discursiva vale (você define)
pontos_por_objetiva = (1000 - peso_discursiva) / 31
nota_objetivas = acertos_objetivas × pontos_por_objetiva
nota_discursiva = (pontos_da_discursiva / pontos_máximos_da_discursiva) × peso_discursiva
nota_final = nota_objetivas + nota_discursiva      (máximo: 1000)
```

Por exemplo, com peso da discursiva = 200: cada uma das 31 objetivas vale
(1000-200)/31 ≈ 25,8 pontos, e a discursiva vale até 200 pontos — acertar
tudo nas objetivas e tirar nota máxima na discursiva soma exatamente 1000.
Se a discursiva ainda não foi avaliada, ela entra como 0 pontos ganhos
(mas o espaço dela no total já é considerado) e o app avisa que a nota
está provisória, até você avaliá-la.

**Onde ver essa conversão:** o Histórico mostra, lado a lado, a nota
"bruta" da discursiva (na escala em que foi avaliada, ex.: 7 de 10) e
quantos pontos isso valeu na nota final de 1000 — assim dá pra conferir
que a conversão está sendo aplicada. O Dashboard tem uma aba dedicada
("Discursiva") só com estatísticas dela.

Use esse número como uma referência rápida na mesma faixa (0 a 1000) que o
ENEM usa — **não é o cálculo oficial do INEP** e não deveria ser
apresentado aos alunos como se fosse.

## Tempo de prova

Na página *Corrigir Prova*, marque a caixa "Registrar horário desta prova"
para informar o horário de início e término. O app calcula a duração em
minutos e guarda isso junto com a correção. No *Dashboard*, a aba "Tempo x
Nota" cruza essas durações com as notas (coeficiente de correlação de
Pearson) — mas só considera as correções em que o horário foi preenchido.

## Dashboard

Seis abas:

- **Por turma**: média, mediana, desvio padrão da nota (0-1000), um
  histograma com a curva normal ("gaussiana") sobreposta para visualizar o
  quanto a distribuição real se aproxima de uma distribuição normal, uma
  tabela comparando todas as turmas e, com duas ou mais turmas no filtro,
  um **gráfico de barras** com a média de cada uma e um **boxplot**
  comparando a distribuição completa (mediana, quartis, dispersão) lado a
  lado.
- **Por aluno**: escolha um aluno (dentro do filtro de turma/simulado) e
  veja a média, o desvio padrão (quando há mais de uma correção) e a
  evolução da nota ao longo dos simulados que ele já fez.
- **Ranking**: gráfico de barras destacando os melhores (verde) e piores
  (vermelho) alunos do filtro atual — ajuste quantos mostrar de cada lado
  — mais uma tabela com a classificação completa.
- **Discursiva**: estatísticas focadas só na questão discursiva —
  aproveitamento médio (0-100%, comparável entre simulados mesmo que o
  peso mude), mediana, desvio padrão, histograma com gaussiana, quantos
  pontos de 1000 ela rendeu em média, comparativo entre turmas, e o
  histórico de um aluno específico na discursiva ao longo dos simulados
  que fez. Sem escolher um simulado específico no filtro do topo, os
  números somam **todos os simulados aplicados**.
- **Questões**: com um simulado específico selecionado no filtro, mostra
  um **gráfico de pizza** com a proporção geral de Certo/Errado/Em branco
  (somando todos os alunos filtrados) e o percentual de acerto por
  questão, destacando as mais difíceis.
- **Tempo x Nota**: gráfico de dispersão entre tempo de prova e nota, com
  a reta de tendência e o coeficiente de correlação de Pearson.

## Exportar

Todos os PDFs gerados nesta página (feedback por aluno e Relatório Geral)
saem com um **timbre** em toda página: logo no cabeçalho e, no rodapé,
logo, linha de destaque e dados de contato. O app vem com um **timbre
genérico** ("Nome da Instituição", "SUA LOGO", endereço fictício). Para
colocar o da sua instituição, veja a seção
[Personalizar o timbrado](#personalizar-o-timbrado).

A página *Exportar* baixa os dados das correções filtrados por simulado,
turma e/ou aluno:

- **Dados detalhados**: uma linha por correção (aluno, turma, acertos,
  nota objetiva, nota 0-1000, pontos da discursiva, tempo de prova, data)
  — baixe em **CSV** ou **Excel**.
- **Boletim por turma**: escolha uma turma específica no filtro para gerar
  uma tabela **aluno x simulado** com a nota 0-1000 de cada um e a média
  geral do aluno — também disponível em CSV ou Excel. Útil para uma visão
  geral do semestre de uma turma inteira.
- **Feedback em PDF (um relatório por aluno)**: com um simulado E uma
  turma específicos escolhidos nos filtros, gera um PDF para impressão com
  **uma página por aluno**, contendo:
  - a nota (0-1000) em destaque;
  - um **gráfico da distribuição de notas da turma com a nota do aluno
    marcada** (linha vertical + ponto sobre a curva), para ele ver onde
    está em relação à turma;
  - **sugestão dos temas mais errados** (se você cadastrou os temas das
    questões — ver seção abaixo);
  - o **feedback da questão discursiva** (resumo e justificativas dadas
    pela IA, ou as observações da avaliação manual);
  - a **tabela completa das respostas do aluno comparadas ao gabarito**,
    questão a questão, com Certo/Errado destacado em cor.

  Se algum aluno da turma ainda não tem a discursiva avaliada, um aviso
  aparece antes de gerar — o PDF dele mostra "ainda não avaliada" nesse
  caso, sem travar a geração dos demais.
- **Relatório Geral (PDF)**: um PDF de visão geral (não é por aluno) com
  os mesmos itens do *Dashboard*, para o filtro escolhido no topo da
  página:
  - visão geral (média, mediana, desvio padrão, histograma com gaussiana);
  - comparativo entre turmas (tabela + gráfico de barras + boxplot), se
    houver 2 ou mais turmas no filtro;
  - ranking dos melhores e piores alunos (ajuste quantos mostrar de cada
    lado);
  - desempenho na questão discursiva (aproveitamento médio, distribuição,
    comparativo entre turmas);
  - **desempenho por questão objetiva** — pizza de Certo/Errado/Em branco
    e o percentual de acerto de cada uma das 31 questões, na ordem da
    prova, colorido por faixa (vermelho abaixo de 50%, laranja entre
    50-75%, verde acima disso) — só aparece quando um simulado específico
    está selecionado no filtro (precisa do gabarito dele para calcular);
  - **desempenho por objeto de conhecimento** — a mesma ideia acima, mas
    agregado pelos temas cadastrados em cada questão (ver seção "Temas
    das questões" abaixo), ordenado do que mais precisa de atenção para o
    que já está bem consolidado — útil para saber, por exemplo, se a
    turma precisa reforçar "Banco de dados" ou "Engenharia de requisitos"
    de acordo com os objetos de conhecimento oficiais do Enade;
  - correlação entre tempo de prova e nota (quando há dados suficientes).

## Temas das questões (objetos de conhecimento)

Na página *Simulados e Gabaritos*, depois de definir o gabarito, há uma
seção opcional "Temas das questões" — uma tabela editável para associar
cada uma das 31 questões objetivas a um tema/objeto de conhecimento.

Para facilitar e manter os nomes consistentes, o campo é um menu suspenso
com as listas **oficiais do Enade 2026** extraídas das portarias do
Inep — um expansor logo acima também mostra as duas listas completas
como referência:

- **Formação Geral** — Portaria Inep nº 154/2026 (12 objetos de
  conhecimento, comuns a todos os cursos).
- **Componente específico de Tecnologia em ADS** — Portaria Inep nº
  169/2026 (20 objetos de conhecimento específicos da área).

Se precisar de um tema que não está em nenhuma das duas listas, escolha
"Outro (digite abaixo)" na linha da questão e preencha no campo de texto
que aparece (formato `questão: tema`, uma por linha). Temas customizados
salvos antes dessa lista oficial existir continuam funcionando — eles
aparecem automaticamente como opção extra no menu.

Não é obrigatório preencher, mas quando preenchido, habilita:

- a seção **"Temas a revisar"** no PDF de feedback individual (por aluno)
  — para cada aluno, o app conta quantas questões erradas caem em cada
  tema e lista os que mais precisam de atenção;
- a seção **"Desempenho por objeto de conhecimento"** no **Relatório
  Geral** (página *Exportar*) — agrega o desempenho da turma (ou do
  filtro escolhido) por tema, num gráfico de barras ordenado do pior para
  o melhor, para você ver rapidamente quais objetos de conhecimento da
  prova a turma como um todo mais precisa reforçar.

## Configurações

A página *Configurações* guarda, num arquivo local (`data/config.json`,
separado do banco de correções):

- **Chave de API do Gemini** e **modelo padrão** — usados automaticamente
  como valor inicial do campo de chave em *Corrigir Prova* (ainda dá para
  sobrescrever ali, só para aquela sessão, sem alterar o que está salvo).
- **Sensibilidade mínima de preenchimento** e **margem relativa** — valores
  padrão dos sliders de "Ajuste fino da leitura" (tanto no gabarito quanto
  na correção das provas).
- **Nota máxima padrão da questão discursiva** — usada quando um simulado
  não tem rubrica cadastrada (modo de pontuação manual). Isso é a escala
  em que você pontua a discursiva (ex.: 0 a 10) — diferente do próximo item.
- **Peso da discursiva na nota final (0-1000)** — quantos dos 1000 pontos
  totais a questão discursiva vale; o restante é dividido igualmente entre
  as 31 questões objetivas. Ver a seção "Nota na escala 0-1000" acima para
  a fórmula completa.

**Atenção (segurança):** isso não é um cofre de segredos — é um arquivo
JSON em texto puro, pensado para uso local/pessoal (equivalente a guardar
a chave numa variável de ambiente). Qualquer pessoa com acesso a essa
pasta no disco consegue ler a chave salva ali.

## Onde os dados ficam salvos

Tudo é gravado em `data/gabarito_app.db` (SQLite), na mesma pasta do app —
**não é preciso recarregar o gabarito ou reprocessar nada a cada sessão**.
Principais tabelas:

- `simulados` — nome, número de questões, gabarito (JSON), rubrica da
  questão discursiva (texto) e observações.
- `turmas` — nome e observações.
- `alunos` — nome, turma (vínculo com `turmas`) e observações.
- `correcoes` — simulado, aluno/turma (nome e vínculo com os cadastros),
  respostas objetivas (JSON), acertos, nota objetiva (%), nota na escala
  0-1000, horário de início/fim e duração da prova, e (se aplicável)
  pontos da discursiva, avaliação da IA e caminho da foto da resposta
  discursiva.

Fotos das respostas discursivas ficam em `data/discursivas/`.

**Atenção:** se você publicar este app num serviço com armazenamento
efêmero (alguns provedores de deploy gratuito reiniciam o container do
zero a cada deploy/reinício), o banco e as fotos podem ser perdidos. Para
uso contínuo em produção, rode localmente / num servidor com disco
persistente, ou aponte `DB_PATH` (em `db.py`) e `DISCURSIVAS_DIR` (em
`pages/2_Corrigir_Prova.py`) para um disco persistente.

## Avaliação da questão discursiva (32) com IA (Google Gemini)

A questão 32 é dissertativa e não é lida pelo OMR. Na página *Corrigir
Prova* (modo Individual), depois de processar o cartão de respostas
objetivas, você sempre vê uma segunda seção para enviar a **foto da
resposta discursiva** — ou seja, uma correção completa envolve **duas
imagens**: o cartão de respostas e a folha da discursiva. No modo Em
lote, anexar a foto da discursiva é opcional em cada item — dá pra deixar
para avaliar depois (ver seção seguinte).

O que aparece nessa seção depende de o simulado ter uma **rubrica**
cadastrada (na página *Simulados e Gabaritos*):

**Com rubrica definida** — fluxo assistido por IA:

1. Fotografe a resposta discursiva do aluno.
2. Confira o campo **"Chave da API do Gemini"** — ele já vem preenchido
   automaticamente se você salvou uma chave na página *Configurações*
   (também aceita a variável de ambiente `GEMINI_API_KEY` como alternativa).
   Pode digitar/trocar aqui só para esta sessão, sem alterar o que está
   salvo em Configurações.
3. Clique em **"Avaliar com IA (Gemini)"**. O app envia a imagem + a
   rubrica para a API do Gemini (modelo definido em *Configurações*, com
   visão) e recebe: uma **transcrição** do que a IA leu na resposta
   manuscrita, uma pontuação sugerida por item e uma justificativa.
4. **Revise a transcrição.** Como a resposta vem manuscrita, a IA pode
   errar a leitura de trechos com letra difícil — a transcrição aparece
   num campo de texto editável para você corrigir o que estiver errado.
5. Depois de corrigir, clique em **"Reavaliar com transcrição corrigida"**
   para pedir uma nova sugestão de pontuação com base só no texto revisado
   (mais confiável do que reavaliar em cima da imagem de novo).
6. **A pontuação final vem em campos editáveis** — você sempre revisa e
   ajusta antes de salvar, com ou sem usar a IA. Isso nunca é uma nota
   automática definitiva.

**Sem rubrica definida** — modo simples: a seção mostra só o upload/foto
da resposta discursiva, um campo de nota máxima, um campo de nota atribuída
manualmente e um campo de observações. A foto continua sendo salva junto
com a correção mesmo sem usar IA.

Pontos importantes:

- **Custo**: cada avaliação consome créditos/cota da sua conta Google
  (cobrança por token, incluindo os tokens da imagem). Consulte
  ai.google.dev/pricing. O AI Studio costuma liberar uma chave gratuita
  para testes, mas com uso e retenção de dados diferentes do plano pago
  (veja o próximo ponto).
- **Privacidade — atenção especial aqui**: a política do Gemini muda
  bastante dependendo do tipo de chave:
  - **Chave gratuita (AI Studio, sem cobrança vinculada)**: o Google
    **usa** os prompts e arquivos enviados (inclusive imagens) para
    melhorar os produtos deles, podendo incluir revisão humana.
  - **Chave paga (com conta de cobrança vinculada)**: o Google **não**
    usa os prompts/respostas para treinar modelos — mas ainda registra
    (loga) as requisições por um período limitado para monitoramento de
    abuso.
  
  **Para dados reais de alunos, use uma chave com cobrança vinculada
  (paga)** — não a chave gratuita padrão do AI Studio. Mesmo na chave
  paga, se quiser reter menos dados ainda, existe a opção de *Zero Data
  Retention* nos termos da API do Gemini (Vertex AI/Google Cloud). Se
  isso for sensível na sua instituição, considere também cobrir nome/CPF
  na foto antes de enviar.
- **Não é 100% confiável, especialmente por ser manuscrito**: modelos de
  visão como o Gemini lidam bem melhor com caligrafia do que OCR
  tradicional (eles interpretam a imagem inteira, não caractere por
  caractere), mas ainda podem errar a leitura em letra ruim, texto
  apertado ou foto de baixa qualidade. É exatamente por isso que a
  transcrição fica editável antes da nota ser calculada — sempre confira
  o que a IA "leu" contra a foto original.
- A **nota da discursiva é registrada separadamente** da nota das 31
  questões objetivas (não são somadas automaticamente) — como combinar as
  duas no boletim final fica a critério seu.
- Se você não quiser usar IA, pode simplesmente não clicar em "Avaliar com
  IA" e preencher a pontuação manualmente nos mesmos campos, usando a foto
  como referência.

## Correção individual x em lote

Na página *Corrigir Prova*, escolha o modo no topo:

**Individual** — uma prova por vez: turma, aluno, foto do cartão, revisão,
discursiva (se quiser) e horário — como descrito nas seções acima.

**Em lote** — para corrigir várias provas de uma vez:

1. Escolha o simulado e uma **turma padrão** para o lote (pode trocar
   turma/aluno individualmente depois, então funciona mesmo se o lote
   misturar turmas).
2. Envie **várias fotos do cartão de respostas de uma vez** (upload
   múltiplo — só imagens jpg/png neste modo; PDF e câmera continuam
   disponíveis no modo Individual). O app lê todas automaticamente.
3. Para cada foto, um cartão de revisão mostra a imagem anotada e o
   número de acertos já no título — você só precisa: selecionar o aluno
   cadastrado (ou digitar um nome novo, que é cadastrado na hora de
   salvar) e, se quiser, abrir "Revisar leitura" para corrigir alguma
   marcação lida errado.
4. **Discursiva no lote é opcional por foto**: marque a caixa "Anexar
   foto da resposta discursiva" se quiser já tirar a foto agora — ela é
   salva junto, mas **sem nota ainda** (avaliar 30 discursivas em fila,
   uma a uma, no meio do lote, seria bem mais lento que fazer isso depois
   com calma — por isso o lote não roda a IA por item). Se preferir, pule
   e anexe a foto depois.
5. Clique em **"Salvar N correção(ões)"** — só entram no histórico os
   itens que já têm aluno definido; os demais ficam pendentes até você
   completar os dados e enviar de novo.

## Avaliando a discursiva depois

Se uma correção foi salva sem nota na discursiva (comum no modo Em lote),
vá em **Histórico** → seção **"Questão discursiva"**, escolha a correção
e abra "Avaliar / reavaliar a discursiva desta correção". Funciona igual
à tela de correção individual (IA com transcrição editável, ou manual) —
com uma diferença: se já havia uma foto anexada (do lote), ela aparece
pronta para usar, sem precisar reenviar. Ao salvar, a **nota 0-1000 dessa
correção é recalculada automaticamente** com o novo valor da discursiva.
Essa mesma tela também serve para **corrigir** uma nota de discursiva já
lançada (repita a avaliação — ela substitui a anterior).

## Como funciona a leitura óptica (OMR)

Ver detalhes técnicos do pipeline (correção de perspectiva calibrada pela
moldura da tabela de questões + leitura por template) nos comentários de
`omr_utils.py`. Resumo: como o cartão é sempre o mesmo, a posição de cada
uma das 155 bolhas (31 questões × 5 alternativas) foi extraída do PDF
oficial e calibrada em relação à moldura da tabela de questões (mais
confiável de detectar em fotos do que a página inteira).

**Em toda tela onde uma leitura automática acontece (gabarito ou prova do
aluno), a tabela de respostas detectadas fica editável antes de salvar** —
use isso para corrigir qualquer marcação lida errado (iluminação ruim,
foto tremida, caneta muito clara etc.) antes de confirmar.

### Ajuste fino da leitura

Cada tela com leitura automática tem um expansor **"Ajuste fino da
leitura"** com dois controles:
- **Sensibilidade mínima de preenchimento** — quão "escura" uma bolha
  precisa estar para ser considerada marcada.
- **Margem relativa** — quanto a bolha marcada precisa se destacar das
  outras 4 da mesma questão.

## Limitações conhecidas / próximos passos

- Calibrado **especificamente para este template** de cartão (31 questões,
  5 alternativas, duas colunas). Se o layout mudar, é preciso gerar um novo
  `template_gabarito.json`.
- Funciona melhor com fotos bem enquadradas, mostrando a tabela de
  questões inteira, de frente e com boa iluminação.
- Rasuras/marcações duplas não são tratadas de forma especial — o sistema
  pega a bolha com mais pixels escuros dentro da margem configurada; a
  revisão manual antes de salvar é a rede de segurança para esses casos.
- Login controla quem entra, mas **não segrega dados entre contas** —
  qualquer usuário logado vê e edita todos os simulados, turmas, alunos e
  correções (ver seção "Login" acima).
- Exclusão de simulado apaga em cascata todas as correções associadas
  (há uma confirmação explícita antes).
- A **nota 0-1000 não é o cálculo oficial do INEP** (TRI) — é uma
  conversão proporcional simples. Ver a seção "Nota na escala 0-1000"
  acima antes de divulgar esse número para os alunos.
- O Dashboard usa a nota 0-1000 como referência principal; correções
  antigas (feitas antes dessa funcionalidade existir) não têm esse valor
  calculado e não entram nos gráficos/estatísticas até serem recalculadas
  (não há um botão de recálculo em lote — seria um próximo passo natural).
- **Mudar o peso da discursiva em Configurações não recalcula
  correções já salvas** — o peso vale para as próximas correções (ou para
  qualquer correção que você abrir e salvar de novo em *Recorrigir*).
  Se você mudar o peso no meio da correção de uma turma, as provas
  corrigidas antes e depois da mudança usam pesos diferentes, a não ser
  que você reabra e resalve as anteriores em *Recorrigir*.
- O PDF de feedback compara a nota do aluno com a **distribuição da turma
  filtrada no momento da geração** — se você gerar o PDF antes de terminar
  de corrigir todos os alunos, a comparação reflete só quem já foi
  corrigido até ali.
- Os "temas das questões" são só texto livre por questão, sem hierarquia
  nem vínculo com um banco de conteúdos — é só o que você escrever na
  tabela em Simulados e Gabaritos.
- A correlação tempo x nota só é calculada com correções que tiveram o
  horário de início/fim preenchido manualmente na tela de correção.
- O modo Em lote não aceita PDF nem câmera (só upload múltiplo de
  imagens) — use o modo Individual para esses casos.
- No modo Em lote, o horário de início/fim não é registrado por item
  (ficaria repetitivo digitar para cada foto) — se precisar do tempo de
  prova, use o modo Individual.

## Personalizar o timbrado

O timbre que sai nos PDFs é montado por `_desenhar_timbre()`, em
`pdf_reports.py`. Ele usa duas imagens e um bloco de texto:

```
┌──────────────────────────────────────────────┐
│        [ assets/logo_cabecalho.png ]         │  ← cabeçalho, centralizado
│                                              │
│              (conteúdo do PDF)               │
│                                              │
│ ──────────────────────────────────────────── │  ← linha de destaque
│ [ assets/logo_rodape.png ]  Nome da Instit.  │
│                             Endereço...      │  ← _RODAPE_LINHAS
│                             CEP / Tel. ...   │
└──────────────────────────────────────────────┘
```

### 1. Trocar os logos

Substitua os dois arquivos em `assets/` **mantendo os mesmos nomes**:

| Arquivo | Onde aparece | Tamanho no PDF | Proporção | Sugestão de imagem |
|---|---|---|---|---|
| `logo_cabecalho.png` | topo de cada página | 8,7 × 2,2 cm | ~3,9 : 1 (largura : altura) | 842 × 216 px ou maior |
| `logo_rodape.png` | canto inferior esquerdo | 4,1 × 1,8 cm | ~2,3 : 1 | 325 × 140 px ou maior |

Dicas:
- Use **PNG com fundo transparente**. Fundo branco também funciona, mas
  aparece como um retângulo se a página não for branca.
- Imagens com outra proporção **não são esticadas**: elas são reduzidas até
  caber na área, mantendo a proporção. Se o logo ficar pequeno demais,
  recorte as bordas vazias da imagem.
- Se você só tem o timbrado em PDF ou Word, dá para extrair os logos
  originais: no `.docx`, renomeie para `.zip` e veja a pasta `word/media/`;
  no PDF, use `pdfimages -png timbrado.pdf logo` (pacote poppler-utils).
- Se um dos arquivos não existir, o PDF é gerado normalmente, só sem
  aquele logo.

### 2. Trocar os textos do rodapé

Em `pdf_reports.py`, edite a lista `_RODAPE_LINHAS`. Altere **só o texto**
(primeiro item de cada linha). Os números são a altura de cada linha na
página e podem ficar como estão:

```python
_RODAPE_LINHAS = [
    # (texto, y_reportlab, negrito, cor)
    ("Faculdade Exemplo de Tecnologia", 88.62, True, _COR_CINZA_ESCURO),
    ("Rua das Flores, 100 – Centro – São Paulo/SP", 76.60, False, _COR_CINZA_ESCURO),
    ("CEP: 01000-000", 64.60, False, _COR_CINZA_ESCURO),
    ("Tel.: (11) 1234-5678", 64.60, False, _COR_CINZA_CLARO),
    ("e-mail: contato@faculdadeexemplo.edu.br", 52.60, False, _COR_CINZA_CLARO),
    ("www.faculdadeexemplo.edu.br", 40.60, False, _COR_CINZA_CLARO),
]
```

Observações:
- A linha que começa com `Tel.:` é desenhada **na mesma altura do CEP**, mais
  à direita (posição em `_RODAPE_TEL_X`). Se mudar o prefixo "Tel.:", ela
  passa a ser desenhada no mesmo lugar do CEP, por cima dele. Nesse caso,
  mude também a altura dela.
- Para **remover** uma linha (por exemplo, o site), apague-a da lista.
- Para **acrescentar** uma linha, use uma altura entre 40 e 100 que não
  coincida com as outras. As linhas ficam a cerca de 12 pontos uma da outra.
- Textos muito longos (mais de uns 60 caracteres) passam da margem
  direita. Nesse caso, quebre em duas linhas.

### 3. Trocar a cor da linha de destaque (opcional)

Em `pdf_reports.py`, o campo `cor` de `_LINHA_DESTAQUE` usa RGB de 0 a 1.
Para converter uma cor de 0-255, divida cada valor por 255:

```python
# azul-marinho (padrão genérico): RGB 31, 58, 95
_LINHA_DESTAQUE = dict(..., cor=(31 / 255, 58 / 255, 95 / 255))
# vermelho: RGB 218, 37, 29
_LINHA_DESTAQUE = dict(..., cor=(218 / 255, 37 / 255, 29 / 255))
```

Para não ter linha nenhuma, use `altura=0`.

### 4. Ajustes de posição (só se precisar)

As posições estão em **pontos** (1 cm ≈ 28,35 pt), numa página A4 de
595 × 842 pt, contando a partir do **canto inferior esquerdo**:

- `_CABECALHO_RECT`: posição (`x`, `y`) e tamanho máximo do logo do cabeçalho;
- `_RODAPE_LOGO_RECT`: o mesmo para o logo do rodapé;
- `_RODAPE_TEXTO_X`: onde começa o texto do rodapé;
- `MARGEM_SUPERIOR_COM_TIMBRE` / `MARGEM_INFERIOR_COM_TIMBRE`: espaço
  reservado para o timbre, para que o conteúdo não fique por cima dele.
  Aumente esses valores se seu logo ou rodapé ocupar mais espaço.

### 5. Conferir

Gere qualquer PDF na página *Exportar* (o Relatório Geral é o mais rápido).
Os arquivos `timbrado.pdf` e `timbrado.docx`, na raiz do projeto, mostram
o timbre genérico e servem de modelo para documentos feitos à mão. **O app
não usa esses dois arquivos**: o que vale nos PDFs é o que está em
`assets/` e `pdf_reports.py`. Se quiser que eles fiquem iguais ao seu
timbre, edite o `.docx` no Word (cabeçalho e rodapé) e exporte o PDF.

## Privacidade e limpeza dos dados (LGPD)

O banco `data/gabarito_app.db` guarda **dados pessoais de alunos**: nome,
matrícula, turma, respostas, notas, horários de prova e a transcrição feita
pela IA das respostas manuscritas da discursiva. As fotos dessas respostas
ficam em `data/discursivas/`. Trate a pasta `data/` como confidencial.

### Por que "apagar" não basta no SQLite

Um `DELETE` no SQLite **não remove o conteúdo do arquivo**: ele só marca as
páginas como livres para reaproveitamento. Até que sejam sobrescritas, os
registros antigos (nomes, matrículas, notas, transcrições, hashes de senha)
continuam no arquivo `.db` e **podem ser recuperados** com ferramentas
simples de análise forense, mesmo com todas as tabelas aparecendo vazias.

Por isso, a rotina `apagar_todos_os_dados()` (em `sample_data.py`) executa
um **`VACUUM`** depois de apagar. O `VACUUM` reescreve o banco do zero,
sem as páginas livres. Se você apagar dados por outro caminho (outro
script, um editor de SQLite etc.), rode o `VACUUM` manualmente:

```bash
python -c "import sqlite3; c = sqlite3.connect('data/gabarito_app.db'); c.execute('VACUUM'); c.close()"
```

Para conferir que não ficou nada, `PRAGMA freelist_count;` deve retornar `0`.

### Antes de compartilhar o app (zip, repositório, outro professor)

1. Rode `apagar_todos_os_dados(apagar_usuarios=True)`, que já inclui o `VACUUM`.
   Ou então não envie o arquivo `data/gabarito_app.db`: o app cria um banco
   novo e vazio na primeira execução.
2. Confirme que `data/discursivas/` está vazia.
3. Confira se `data/config.json` está **sem chaves de API**.
4. Remova as pastas `__pycache__/`. Os arquivos `.pyc` guardam o caminho
   completo da pasta do app no seu computador.
5. **Não deixe no pacote listas de presença, planilhas de turma ou outros
   arquivos usados para importar alunos.** Eles contêm nomes e matrículas.
6. Não versione a pasta `data/` em repositórios Git. Coloque `data/` e
   `__pycache__/` no `.gitignore`.

### Histórico desta versão

Esta cópia ("appCorrecaoBlank") foi higienizada em 12/11/2026:

- o banco foi reconstruído com `VACUUM`. Ele tinha restos recuperáveis de
  3 simulados e 103 correções de uma turma real, além do cadastro dos alunos
  e de um usuário;
- foram removidos `ListaPresenca.pdf` (lista de presença com nomes e
  matrículas) e `__pycache__/`;
- `apagar_todos_os_dados()` passou a executar `VACUUM` ao final;
- o timbre da instituição foi substituído por um timbre genérico (logos,
  textos do rodapé, `timbrado.pdf` e `timbrado.docx`).

## Estrutura

```
gabarito_enade/
├── app.py                       # página inicial (resumo, navegação)
├── config.py                     # configurações locais (chave de API, padrões de leitura)
├── db.py                        # persistência SQLite (simulados, turmas, alunos, correções)
├── ui_common.py                 # captura de imagem + OMR + tabela de revisão (compartilhado)
├── omr_utils.py                  # correção de perspectiva + leitura por template
├── gemini_grading.py             # integração com a API do Google Gemini p/ avaliação da discursiva
├── scoring.py                     # nota na escala 0-1000 e cálculo do tempo de prova
├── stats_utils.py                 # estatísticas e gráficos do Dashboard
├── import_utils.py                # leitura de planilhas de turma (importação de alunos)
├── auth.py                        # gate de login (usuário/senha, PBKDF2)
├── pdf_reports.py                 # gera os PDFs exportáveis (feedback por aluno + relatório geral), com timbre institucional
├── enade_referencia.py            # listas oficiais dos objetos de conhecimento do Enade 2026 (portarias Inep 154/169)
├── sample_data.py                 # apagar todos os dados (com VACUUM) e gerar dataset sintético de exemplo
├── template_gabarito.json        # posição calibrada de cada bolha
├── assets/
│   ├── logo_cabecalho.png        # logo do timbre (cabeçalho dos PDFs) — genérico, substituível
│   └── logo_rodape.png           # logo do timbre (rodapé dos PDFs) — genérico, substituível
├── pages/
│   ├── 1_Simulados_e_Gabaritos.py
│   ├── 2_Corrigir_Prova.py
│   ├── 3_Historico.py
│   ├── 4_Configuracoes.py
│   ├── 5_Turmas_e_Alunos.py
│   ├── 6_Dashboard.py
│   ├── 7_Recorrigir.py
│   └── 8_Exportar.py
├── data/
│   ├── gabarito_app.db           # criado automaticamente na primeira execução
│   ├── config.json               # criado ao salvar em Configurações
│   └── discursivas/              # fotos das respostas discursivas
├── timbrado.pdf / timbrado.docx   # modelo do timbre genérico (não usado pelo app)
├── requirements.txt
└── README.md
```
