# Gestão da Loja — Obreiros e Financeiro

Sistema web em **Python + Streamlit** para gestão de obreiros e do financeiro
de uma Loja Maçônica, com **login e dois níveis de acesso**. O banco é
**SQLite local** por padrão e pode ser migrado para a nuvem apenas trocando a
variável `DATABASE_URL` (a aplicação usa SQLAlchemy, sem SQL preso ao SQLite).

Para deixar de depender do seu computador, siga o guia
**[Publicar na nuvem](DEPLOY_NUVEM.md)**: aplicação no Streamlit Community
Cloud + banco Postgres no Neon/Supabase, incluindo a migração dos dados atuais.

## Perfis de acesso

| Perfil | O que pode fazer |
| --- | --- |
| **Administrador** (Presidente, Tesoureiro, Secretário) | Visualizar tudo, cadastrar/editar/excluir obreiros, lançar entradas e saídas, gerar mensalidades, dar baixa/estornar mensalidades e gerenciar usuários. |
| **Membro** | Visualizar a lista de obreiros (somente leitura), o fluxo de caixa consolidado da Loja e o próprio status financeiro (mensalidades e contribuições). Não vê formulários nem botões de edição. |

O controle é aplicado em dois níveis: o menu é montado conforme o perfil e cada
página administrativa também valida a permissão antes de renderizar.

## Navegação

O menu lateral tem três áreas:

1. **Secretaria** — cadastro e listagem dos obreiros (nome, CIM, grau, status,
   CPF, telefone e e-mail). Para administradores há também:
   - **Criar acesso ao sistema**: gera o login inicial do obreiro (o próprio
     CIM) com a senha temporária `123456`, sem redigitar os dados;
   - **Editar ou excluir obreiro** e a aba de usuários, com redefinição de
     senhas.

   Membros veem apenas a lista, sem dados pessoais e sem botões de edição.
2. **Tesouraria** — exclusiva de administradores. Divide-se em:
   - **Lançamentos**: registro de receitas e despesas, totais do mês e
     exclusão de lançamentos.
   - **Capitação (mensalidades)**: geração em lote, baixa por obreiro
     selecionado (criando a mensalidade se ainda não existir) e estorno.
3. **Relatórios** — disponível para todos, com o saldo acumulado da Loja,
   gráfico de entradas vs. saídas (6 ou 12 meses) e a relação de obreiros com
   mensalidades atrasadas. Para o membro, a lista e os totais de atraso são
   limitados ao próprio obreiro, e há ainda o detalhamento em **Minha situação
   financeira**. Para administradores, há também o **demonstrativo financeiro
   em PDF**.

Consideram-se atrasadas as competências **pendentes anteriores ao mês atual**.
Cada ação de escrita (cadastrar, lançar, baixar, estornar) é confirmada no
banco por transação e a tela é recarregada em seguida com os dados atualizados.

## Primeiro acesso e credenciais temporárias

Na primeira execução, como não há usuários cadastrados, o sistema exibe a tela
**Configuração inicial** para criar o primeiro **Administrador**. Esse primeiro
administrador já entra com as credenciais definitivas que acabou de definir.

Para os demais usuários:

1. O administrador cadastra os obreiros em **Secretaria**.
2. Em **Secretaria › Criar acesso ao sistema**, escolhe o obreiro e clica em
   **Criar acesso**. O sistema usa o **CIM** como login inicial e a senha
   **123456**, vinculando o acesso ao obreiro automaticamente. (A criação
   manual, com login e senha escolhidos pelo administrador, continua
   disponível no menu **Usuários**.)
3. Entrega o login e a senha temporários ao obreiro.
4. No **primeiro acesso**, o sistema bloqueia todas as páginas e exige que o
   usuário defina um **novo login** e uma **nova senha**.
5. A partir daí, somente as novas credenciais funcionam. O login temporário
   deixa de existir e o usuário segue para as páginas do seu perfil.

Regras da troca:

- O novo login deve ser diferente do login temporário e continuar único.
- A nova senha deve ter pelo menos 6 caracteres e ser diferente da temporária.
- A senha é confirmada duas vezes na tela.
- Enquanto a troca não for concluída, nenhuma página do sistema é liberada.

Se o administrador redefinir a senha de alguém em **Secretaria › Acessos ao
sistema › Gerenciar usuário**, a opção **Exigir troca de login e senha no
próximo acesso** já vem marcada, permitindo entregar uma nova senha temporária.
A coluna **Troca pendente** na lista de usuários mostra quem ainda não concluiu
a troca.

## Funcionalidades

- Login com senha protegida por PBKDF2-HMAC-SHA256 (salt individual).
- Primeiro acesso obrigatório com troca de login e senha temporários.
- Sessão com verificação do usuário a cada execução: desativar um acesso ou
  mudar o perfil passa a valer imediatamente.
- Relatórios com saldo acumulado, gráfico mensal e inadimplência de
  mensalidades.
- Cadastro, busca, edição e exclusão de obreiros (administrador).
- Registro de entradas e saídas, com vínculo opcional ao obreiro.
- Capitação por competência (mês/ano), com geração em lote, baixa por obreiro
  selecionado (que lança a entrada no financeiro) e estorno.
- Vencimento no **dia 20** de cada mês e alerta vermelho para a administração
  quando um obreiro completa **dois meses** de mensalidades vencidas.
- **Recibo por e-mail** automático ao dar baixa numa capitação (opcional,
  depende da configuração de SMTP).
- **Demonstrativo financeiro em PDF** por mês ou período personalizado, com
  entradas, saídas, resultado, saldo acumulado e a lista de lançamentos.
- Situação financeira do membro dentro de **Relatórios**: mensalidades
  pagas/em aberto e contribuições do ano.
- Gestão de usuários: criação, redefinição de senha, indicação de troca
  obrigatória e ativação/desativação.

## Vencimento e inadimplência

- A mensalidade de cada competência vence no **dia 20** do próprio mês.
- Do dia 21 em diante, enquanto estiver pendente, a competência conta como
  atrasada.
- Em **Tesouraria** e em **Relatórios**, administradores veem um aviso vermelho
  com os obreiros que já acumulam **2 ou mais competências vencidas**, com as
  competências e o valor total em aberto.
- A data de vencimento aparece na tabela de mensalidades e pode ser alterada em
  `constants.py` (`DIA_VENCIMENTO`).

## Recibo por e-mail

Ao registrar o pagamento de uma capitação, o sistema envia um recibo em HTML
para o **e-mail cadastrado do obreiro**. Se o envio falhar (rede, senha de app
inválida etc.), o pagamento é registrado normalmente e a tela avisa o motivo.

Configuração (Streamlit Cloud › **Settings › Secrets**, ou `.env` local):

```toml
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "seuemail@gmail.com"
SMTP_PASSWORD = "senha-de-app-do-gmail"
SMTP_FROM = "Loja Maçônica <seuemail@gmail.com>"
NOME_LOJA = "Loja Maçônica ... nº ..."
```

- Sem essas chaves o envio fica desativado e o restante do sistema não muda.
- No Gmail é obrigatório usar uma **senha de app** (com verificação em duas
  etapas ativa); a senha normal da conta é recusada pelo Google.
- A porta 465 (SSL) também é suportada; qualquer outra usa STARTTLS.

## Demonstrativo financeiro em PDF

Em **Relatórios** (visível para administradores), a seção **Demonstrativo
financeiro em PDF** permite escolher:

- **Mês** — basta selecionar mês e ano; ou
- **Personalizado** — data inicial e final.

O arquivo traz o nome da Loja, o período, a data de emissão, o resumo de
**entradas**, **saídas**, **resultado do período** e **saldo acumulado**, além
da lista completa de lançamentos (data, tipo, descrição, obreiro e valor).

- Clique em **Baixar demonstrativo em PDF** e o arquivo é salvo no computador.
- Para **imprimir**, abra o PDF e use `Ctrl+P` (ou `Cmd+P` no Mac).
- O PDF é gerado pelo **ReportLab** dentro do próprio app, sem serviços
  externos; por isso a dependência `reportlab` está no `requirements.txt`.
- Lançamentos com descrição longa quebram a linha automaticamente e o
  cabeçalho da tabela se repete nas páginas seguintes.

## Como rodar

Pré-requisito: Python 3.10 ou superior.

```bash
cd gestao-loja-maconica
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

O navegador abre em `http://localhost:8501`. O banco é criado automaticamente
em `data/loja.db` na primeira execução. Alterações aditivas de esquema são
aplicadas automaticamente a bancos já existentes.

O arquivo `.streamlit/config.toml` já configura o servidor para escutar em
`0.0.0.0:8501`, permitindo acesso de outros dispositivos da rede.

## Acesso pela rede local

No computador que executa o sistema:

```bash
hostname -I
```

Use o primeiro endereço IPv4 retornado. Em outro dispositivo da mesma rede,
acesse:

```text
http://192.168.x.x:8501
```

Se não abrir, verifique o firewall do computador servidor, liberando a porta
TCP 8501:

```bash
# Ubuntu/Debian com ufw
sudo ufw allow 8501/tcp
```

## Acesso pela internet

O sistema já está pronto para publicação. Escolha uma das opções abaixo.

### Opção 1 — Túnel Cloudflare (rápido e temporário)

Útil para testar com os obreiros sem contratar servidor. O endereço muda a cada
execução.

```bash
# Instale o cloudflared (Ubuntu/Debian)
# https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:8501
```

O comando exibe uma URL pública parecida com:

```text
https://algo-aleatorio.trycloudflare.com
```

Envie essa URL aos usuários. Enquanto o comando estiver rodando, o sistema fica
acessível de qualquer dispositivo conectado à internet. Encerre com `Ctrl+C`.

> O túnel rápido é público e temporário. Para uso permanente, use um túnel
> nomeado com domínio próprio ou a opção 2.

### Opção 2 — Servidor com domínio e HTTPS (produção)

1. Contrate uma VPS (ou use um servidor da Loja com IP fixo) e instale Python.
2. Copie o projeto, crie o virtualenv e instale as dependências.
3. Mantenha o Streamlit escutando apenas em `127.0.0.1:8501` e coloque um proxy
   reverso com HTTPS na frente (Caddy, Nginx ou Traefik).

   Exemplo de `Caddyfile` (HTTPS automático):

   ```caddy
   sistema.sualoja.org.br {
       reverse_proxy 127.0.0.1:8501
   }
   ```

4. Libere no firewall somente as portas 80 e 443. A porta 8501 não deve ficar
   exposta diretamente.
5. Para manter o sistema rodando após fechar o terminal, use `systemd`,
   `tmux` ou `screen`. Exemplo de unidade `systemd`:

   ```ini
   [Unit]
   Description=Gestao da Loja
   After=network.target

   [Service]
   WorkingDirectory=/opt/gestao-loja-maconica
   ExecStart=/opt/gestao-loja-maconica/.venv/bin/streamlit run app.py
   Restart=always
   User=www-data

   [Install]
   WantedBy=multi-user.target
   ```

6. **Importante:** não use SQLite em disco efêmero de plataformas cloud. Use um
   volume persistente ou um banco Postgres gerenciado (veja a seção de
   migração). Sem isso, os dados são perdidos a cada reinício do serviço.

### Opção 3 — Streamlit Community Cloud

1. Publique o projeto em um repositório privado no GitHub.
2. Crie o app em <https://share.streamlit.io> apontando para `app.py`.
3. Em **Settings › Secrets**, cadastre a URL de um Postgres gerenciado:

   ```toml
   DATABASE_URL = "postgresql+psycopg://usuario:senha@host:5432/loja"
   ```

4. Inclua `psycopg[binary]` no `requirements.txt` do deploy.
5. Configure os usuários normalmente pelo próprio sistema após a publicação.

O `database.py` lê `DATABASE_URL` primeiro das variáveis de ambiente e depois
de `.streamlit/secrets.toml` (ou dos *Secrets* do Streamlit Cloud).

## Estrutura do projeto

```
gestao-loja-maconica/
├── app.py              # Interface, login e controle de permissões
├── auth.py             # Hash de senhas, autenticação e usuários
├── crud.py             # Validações e acesso aos dados
├── database.py         # Conexão, sessão, criação/migração das tabelas
├── migrar_para_postgres.py  # Copia os dados do SQLite para o Postgres
├── models.py           # Modelos ORM (obreiros, financeiro, usuários, mensalidades)
├── notificacoes.py     # Recibo de capitação por e-mail (SMTP)
├── constants.py        # Valores de domínio (graus, status, perfis, meses, vencimento)
├── requirements.txt
├── DEPLOY_NUVEM.md     # Passo a passo de publicação na nuvem
├── .env.example        # Exemplo de configuração do banco
├── .streamlit/
│   ├── config.toml     # Tema e configurações do Streamlit
│   └── secrets.toml.example  # Exemplo de DATABASE_URL para a nuvem
└── data/
    └── loja.db         # Banco SQLite (criado em tempo de execução)
```

## Esquema do banco

### `obreiros`

| Coluna | Tipo | Regras |
| --- | --- | --- |
| `id` | INTEGER | PK, autoincremento |
| `nome` | VARCHAR(120) | obrigatório |
| `cim` | VARCHAR(20) | obrigatório, único |
| `grau` | VARCHAR(20) | `Aprendiz`, `Companheiro`, `Mestre` ou `Instalado` |
| `status` | VARCHAR(10) | `Ativo` ou `Inativo` |
| `cpf` | VARCHAR(14) | opcional, validado e único (`000.000.000-00`) |
| `telefone` | VARCHAR(20) | opcional (`(00) 00000-0000`) |
| `email` | VARCHAR(120) | opcional |

### `financeiro`

| Coluna | Tipo | Regras |
| --- | --- | --- |
| `id` | INTEGER | PK, autoincremento |
| `tipo` | VARCHAR(10) | `Entrada` ou `Saída` |
| `descricao` | VARCHAR(200) | obrigatório |
| `valor` | NUMERIC(12,2) | obrigatório, maior que zero |
| `data` | DATE | obrigatório, indexado |
| `id_obreiro` | INTEGER | opcional, FK → `obreiros.id` (`ON DELETE SET NULL`) |

### `usuarios`

| Coluna | Tipo | Regras |
| --- | --- | --- |
| `id` | INTEGER | PK, autoincremento |
| `nome` | VARCHAR(120) | obrigatório |
| `usuario` | VARCHAR(30) | obrigatório, único, sempre em minúsculas |
| `senha_hash` | VARCHAR(255) | PBKDF2 (`pbkdf2_sha256$iterações$salt$hash`) |
| `role` | VARCHAR(20) | `Administrador` ou `Membro` |
| `ativo` | BOOLEAN | padrão `true` |
| `deve_trocar_credenciais` | BOOLEAN | `true` enquanto o primeiro acesso não for concluído |
| `id_obreiro` | INTEGER | opcional, FK → `obreiros.id` (`ON DELETE SET NULL`) |

### `mensalidades`

| Coluna | Tipo | Regras |
| --- | --- | --- |
| `id` | INTEGER | PK, autoincremento |
| `id_obreiro` | INTEGER | FK → `obreiros.id` (`ON DELETE CASCADE`) |
| `mes` / `ano` | INTEGER | competência, único por obreiro |
| `valor` | NUMERIC(12,2) | maior que zero |
| `status` | VARCHAR(10) | `Pendente` ou `Paga` |
| `data_pagamento` | DATE | preenchida na baixa |
| `id_lancamento` | INTEGER | FK → `financeiro.id` (`ON DELETE SET NULL`) |

## Segurança

- As senhas são armazenadas apenas como hash PBKDF2 com salt aleatório por
  usuário; nunca em texto puro.
- O hash e a verificação usam comparação de tempo constante
  (`hmac.compare_digest`).
- Usuários criados pelo administrador recebem credenciais temporárias e só
  entram no sistema depois de definir login e senha próprios.
- O último administrador ativo não pode ser desativado, evitando perda total
  de acesso.
- Para produção, recomenda-se: HTTPS, limite de tentativas de login, backups
  periódicos do banco e política de troca de senha.

## Migração para a nuvem

O passo a passo completo está em **[DEPLOY_NUVEM.md](DEPLOY_NUVEM.md)**.
Resumo:

1. Crie um Postgres no Neon ou Supabase e copie a connection string.
2. Defina a URL em `.env`, `.streamlit/secrets.toml` ou variável de ambiente:

   ```bash
   export DATABASE_URL="postgresql://usuario:senha@host/banco?sslmode=require"
   ```

   ```toml
   # .streamlit/secrets.toml
   DATABASE_URL = "postgresql://usuario:senha@host/banco?sslmode=require"
   ```

   O `database.py` aceita `postgres://` ou `postgresql://` e converte
   automaticamente para o driver `psycopg` (v3), já incluído no
   `requirements.txt`.

3. Para levar os dados atuais do SQLite:

   ```bash
   python migrar_para_postgres.py --destino "postgresql://usuario:senha@host/banco?sslmode=require"
   ```

   Use `--limpar` apenas se quiser substituir dados já existentes no destino.

4. Publique a aplicação no Streamlit Community Cloud (ou outro host) com o
   secret `DATABASE_URL`. Na primeira execução, as tabelas são criadas
   automaticamente; o `init_db()` também aplica migrações aditivas em bancos
   antigos.
5. Mantenha backups automáticos do Postgres. Se usar SQLite, garanta que
   `data/` esteja em volume persistente — nunca em disco efêmero de nuvem.
6. Para evoluir o esquema com segurança em produção, o próximo passo
   recomendado é adotar **Alembic** para versionar migrações.

## Próximos passos sugeridos

- Fechamento mensal e exportação em Excel.
- Backup automático e trilha de auditoria (quem alterou o quê).
- Recuperação de senha por e-mail e segundo fator de autenticação.
- Permissões mais granulares (ex.: Tesoureiro sem acesso a usuários).
- Uso de `st.navigation` e páginas separadas quando o sistema crescer.
