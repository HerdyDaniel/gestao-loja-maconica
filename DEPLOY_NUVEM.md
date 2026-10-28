# Publicar na nuvem — sem depender do seu computador

Este guia usa o caminho mais simples para uma Loja pequena:

```text
Navegador do obreiro
        │ HTTPS
        ▼
Streamlit Community Cloud  ──►  Postgres na nuvem (Neon ou Supabase)
(aplicação rodando 24h)          (dados persistentes e com backup)
```

O **Streamlit Community Cloud** hospeda a aplicação e o **Neon** (ou
**Supabase**) hospeda o banco. Assim, seu computador pode ficar desligado.

> Trocar apenas o banco não basta: se o Streamlit continuar no seu computador,
> o sistema continua dependendo dele. É preciso publicar a aplicação também.

## O que você vai precisar

- Conta no GitHub (o código precisa estar em um repositório).
- Conta no Streamlit Community Cloud: <https://share.streamlit.io>
- Conta no Neon: <https://neon.tech> (ou Supabase: <https://supabase.com>)
- O projeto desta pasta.

Os planos gratuitos são suficientes para o movimento de uma Loja. Consulte os
limites atuais dos provedores.

---

## 1. Criar o banco Postgres

### Opção recomendada: Neon

1. Crie uma conta e um projeto no Neon.
2. Escolha a região mais próxima do Brasil, se disponível.
3. Copie a **connection string** do painel. Use preferencialmente a conexão
   **pooled** (host com `-pooler`), indicada para aplicações web.
4. O formato será parecido com:

   ```text
   postgresql://usuario:senha@ep-xxxx-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require
   ```

5. Guarde essa URL. Ela é a única credencial de que a aplicação precisa.

### Alternativa: Supabase

1. Crie um projeto em <https://supabase.com>.
2. Vá em **Project Settings › Database › Connection string**.
3. Escolha o modo **Session pooler** ou **Transaction pooler** e copie a URL.
4. Mantenha `?sslmode=require` no final.

> Se a senha tiver caracteres especiais (`@`, `#`, `%`, `/` etc.), eles precisam
> ser codificados na URL. Prefira uma senha apenas com letras, números e `-` ou
> `_`.

---

## 2. Colocar o projeto no GitHub

No computador onde está o projeto:

```bash
sudo apt install git       # Linux Mint/Ubuntu, se ainda não tiver
cd /home/herdy/gestao-loja-maconica
git init
git add .
git commit -m "Sistema de gestão da Loja"
```

Crie um repositório **privado** no GitHub e envie:

```bash
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/gestao-loja-maconica.git
git push -u origin main
```

O `.gitignore` já impede o envio de:

- `data/*.db` (banco SQLite local);
- `.env`;
- `.streamlit/secrets.toml`;
- `.venv/`.

**Nunca** coloque a URL do Postgres em um arquivo versionado.

Se preferir não usar Git no terminal, também é possível criar o repositório
privado e enviar os arquivos pela interface web do GitHub, respeitando o
`.gitignore`.

---

## 3. Publicar o Streamlit

1. Acesse <https://share.streamlit.io> e entre com o GitHub.
2. Clique em **Create app** / **New app**.
3. Escolha o repositório, a branch `main` e o arquivo principal `app.py`.
4. Em **Advanced settings**, selecione Python 3.12 (ou a versão disponível) e
   informe os **Secrets**:

   ```toml
   DATABASE_URL = "postgresql://usuario:senha@host/banco?sslmode=require"
   ```

   Pode colar a URL exatamente como o provedor entregou. O sistema converte
   automaticamente para o driver `psycopg` (v3).

5. Clique em **Deploy**.

O `requirements.txt` já inclui `psycopg[binary]`, necessário para o Postgres.

Ao abrir o app pela primeira vez, as tabelas são criadas automaticamente no
Postgres. Se o banco estiver vazio, aparecerá a tela de **Configuração
inicial**.

---

## 4. Migrar os dados do SQLite atual

Faça isso **antes** de criar usuários no banco da nuvem, para o script poder
gravar em um banco vazio.

No computador local, com o virtualenv do projeto:

```bash
cd /home/herdy/gestao-loja-maconica
source .venv/bin/activate

python migrar_para_postgres.py \
  --destino "postgresql://usuario:senha@host/banco?sslmode=require"
```

O script:

- cria as tabelas que faltarem;
- copia `obreiros`, `financeiro`, `usuarios` e `mensalidades` na ordem correta;
- preserva IDs, datas, valores, vínculos e **os hashes das senhas** (ou seja,
  as senhas atuais continuam funcionando);
- ajusta as sequências do Postgres para os próximos cadastros;
- confere o total de registros ao final.

Se o destino já tiver dados, o script se recusa a continuar. Para substituir
tudo (operação destrutiva):

```bash
python migrar_para_postgres.py \
  --destino "postgresql://..." \
  --limpar
```

Ele pedirá a confirmação digitando `MIGRAR`. Para automação, acrescente `--sim`.

Também é possível definir a variável e omitir `--destino`:

```bash
export DATABASE_URL="postgresql://usuario:senha@host/banco?sslmode=require"
python migrar_para_postgres.py
```

---

## 5. Testar e desligar o servidor local

1. Abra a URL pública do Streamlit.
2. Entre com o usuário administrador que já existia.
3. Confira obreiros, lançamentos, mensalidades e relatórios.
4. Crie um usuário de teste e valide a troca obrigatória no primeiro acesso.
5. Só depois desligue o computador local:

   ```bash
   pkill -f "[c]loudflared tunnel"
   pkill -f "[s]treamlit run app.py"
   ```

A partir daí, o sistema funciona sem o seu computador.

---

## 6. Backups

O banco na nuvem é a única fonte de verdade. Configure uma rotina de backup:

```bash
pg_dump "postgresql://usuario:senha@host/banco?sslmode=require" \
  > backup_$(date +%F).sql
```

- **Neon:** oferece histórico/branches e restauração; consulte o plano.
- **Supabase:** oferece backups no painel; confira o plano.
- Guarde cópias fora do provedor (por exemplo, noutro disco ou nuvem).
- Teste a restauração de vez em quando.

Fazer backup apenas do SQLite local **não** protege os dados que já estão na
nuvem.

---

## 7. Segurança e limites do plano gratuito

- A URL do Streamlit é pública, mas os dados exigem login. Não existe
  autocadastro.
- Compartilhe a URL apenas com os obreiros e use senhas fortes,
  principalmente no administrador.
- O sistema ainda não tem limite de tentativas de login nem 2FA. Para uma
  camada extra, use **Cloudflare Access** com um domínio próprio, ou um proxy
  com autenticação na frente do app.
- No plano gratuito, o app pode **dormir** após um período sem uso. O primeiro
  acesso depois disso demora alguns segundos.
- Se o app reiniciar e os dados “sumirem”, verifique se o secret
  `DATABASE_URL` está realmente configurado. Sem ele, o sistema cai no SQLite
  local do servidor, que é temporário na nuvem.
- A coluna **Banco** no menu lateral mostra o banco em uso. Em produção, deve
  aparecer **Postgres**, não **SQLite local**.

---

## 8. Alternativas de hospedagem

Se preferir não usar o Streamlit Community Cloud:

| Opção | Vantagens | Atenção |
| --- | --- | --- |
| **Render / Railway / Fly.io** | Rodam o app em container, bom controle | Podem exigir cartão; use volume persistente ou Postgres |
| **VPS (Hetzner, DigitalOcean, Contabo)** | Controle total, domínio próprio | Você administra sistema, HTTPS, firewall e atualizações |
| **Servidor da Loja com IP fixo** | Dados sob seu controle | Continua dependendo de energia e internet locais |

Em qualquer opção, o banco deve ser Postgres gerenciado ou SQLite em volume
persistente. **Nunca** use SQLite no disco efêmero de uma plataforma cloud.

---

## Problemas comuns

**`ModuleNotFoundError: No module named 'psycopg'`**
O deploy não instalou o `requirements.txt`. Verifique se o arquivo contém
`psycopg[binary]>=3.2,<4` e faça **Reboot**/redeploy do app.

**`connection requires SSL`**
Acrescente `?sslmode=require` ao final da URL.

**`too many connections`**
Use a connection string **pooled** do provedor (host com `-pooler` no Neon ou
Session/Transaction pooler no Supabase).

**A senha tem `@` ou `#` e a conexão falha**
Codifique os caracteres especiais na URL ou troque a senha do banco por uma
apenas com letras, números, `-` e `_`.

**O app abre, mas os dados não aparecem**
Confirme o secret `DATABASE_URL` e veja a coluna **Banco** no menu lateral.
Se estiver como **SQLite local**, o secret não foi aplicado.

**O app demora na primeira abertura**
É o modo de economia do plano gratuito. Aguarde alguns segundos e recarregue.
