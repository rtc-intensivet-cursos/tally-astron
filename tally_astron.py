"""Ponte Tally -> Astron Members (club Intensivet 9656).

Para cada inscrição nova nos formulários do Tally listados em config.json:
  1. cria o aluno na Astron pelo e-mail (se já existir, a Astron devolve o
     cadastro existente, sem duplicar);
  2. libera o plano configurado (ex.: MOVE 2026 - Sala de Comando).

As inscrições já tratadas ficam em processados.json (só o id da inscrição,
sem dados pessoais). Se algo falhar, a inscrição fica para a próxima rodada.

Chaves (variáveis de ambiente, nunca no código):
  TALLY_API_KEY, ASTRON_AM_KEY, ASTRON_AM_SECRET

Uso:
  python tally_astron.py              # roda de verdade
  python tally_astron.py --simular    # só mostra o que faria
  python tally_astron.py --so-email x@y.com   # trata só essa inscrição (teste)
  python tally_astron.py --config teste.json  # usa outra lista de formulários
"""
import base64
import json
import os
import re
import secrets
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_CONFIG = os.path.join(PASTA, "config.json")
ARQ_FEITOS = os.path.join(PASTA, "processados.json")
TALLY = "https://api.tally.so"
ASTRON = "https://api.astronmembers.com.br/v1.0/"


def env(nome):
    v = os.environ.get(nome, "").strip()
    if not v:
        # uso local: lê do arquivo .env ao lado do script
        # (a chave da Astron já existe no PC, em C:\astron-mcp\astron.env)
        for caminho in (os.path.join(PASTA, ".env"), r"C:\astron-mcp\astron.env"):
            if v or not os.path.exists(caminho):
                continue
            for linha in open(caminho, encoding="utf-8-sig"):
                if linha.strip().startswith(nome + "="):
                    v = linha.split("=", 1)[1].strip().strip('"').strip("'")
    if not v or "COLE_AQUI" in v:
        sys.exit(f"Falta a chave {nome}.")
    return v


def pedir(req, tentativas=5):
    for t in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and t < tentativas - 1:
                time.sleep(20 * (t + 1))
                continue
            corpo = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"HTTP {e.code}: {corpo}")


# ---------- Tally ----------
def inscricoes(form_id, chave):
    pagina, todas = 1, []
    while True:
        url = f"{TALLY}/forms/{form_id}/submissions?filter=completed&limit=500&page={pagina}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {chave}", "User-Agent": "tally-astron/1.0"})
        r = pedir(req)
        titulos = {q["id"]: (q.get("title") or "").strip().lower() for q in r.get("questions", [])}
        for s in r.get("submissions", []):
            dados = {}
            for resp in s.get("responses", []):
                t = titulos.get(resp.get("questionId"), "")
                dados[t] = resp.get("answer")
            todas.append({"id": s["id"], "quando": s.get("submittedAt"), "dados": dados})
        if not r.get("hasMore"):
            return todas
        pagina += 1


def campo(dados, *nomes):
    for n in nomes:
        v = dados.get(n)
        if isinstance(v, list):
            v = v[0] if v else ""
        if v:
            return str(v).strip()
    return ""


# ---------- Astron ----------
def astron(metodo, params, cab):
    corpo = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(ASTRON + metodo, data=corpo, method="POST", headers={
        "Authorization": cab, "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "tally-astron/1.0"})
    r = pedir(req)
    if not r.get("success", False):
        raise RuntimeError(f"{metodo}: {r.get('error_message') or r}")
    return r.get("return")


def sem_dados(texto):
    """Tira e-mails e números longos (CPF/telefone) de qualquer mensagem:
    o histórico do GitHub é público."""
    texto = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<e-mail>", str(texto))
    return re.sub(r"\d{8,}", "<número>", texto)


def senha_aleatoria():
    letras = string.ascii_letters + string.digits
    return "".join(secrets.choice(letras) for _ in range(10))


def main():
    simular = "--simular" in sys.argv
    so_email = None
    if "--so-email" in sys.argv:
        so_email = sys.argv[sys.argv.index("--so-email") + 1].strip().lower()

    arq_config = ARQ_CONFIG
    if "--config" in sys.argv:
        arq_config = os.path.join(PASTA, sys.argv[sys.argv.index("--config") + 1])
    config = json.load(open(arq_config, encoding="utf-8"))
    feitos = json.load(open(ARQ_FEITOS, encoding="utf-8")) if os.path.exists(ARQ_FEITOS) else {}
    chave_tally = env("TALLY_API_KEY")
    cab = "Basic " + base64.b64encode(
        f"{env('ASTRON_AM_KEY')}:{env('ASTRON_AM_SECRET')}".encode()).decode()
    club, plano = config["club_id"], config["plan_id"]

    novos = erros = 0
    for form in config["formularios"]:
        for s in inscricoes(form["id"], chave_tally):
            if s["id"] in feitos:
                continue
            d = s["dados"]
            email = campo(d, "e-mail", "email").lower()
            nome = campo(d, "nome completo", "nome")[:40]
            fone = re.sub(r"\D", "", campo(d, "whatsapp", "telefone"))
            if so_email and email != so_email:
                continue
            if not email or "@" not in email or len(nome) < 3:
                print(f"[pulei] {form['nome']}: inscrição {s['id']} sem e-mail/nome válido")
                continue
            if simular:
                print(f"[simulação] {form['nome']}: inscrição {s['id']} -> plano {plano}")
                continue
            try:
                p = {"club_id": club, "name": nome, "email": email,
                     "password": senha_aleatoria(), "send_welcome": 1}
                if 10 <= len(fone) <= 19:
                    p["phone"] = fone
                astron("createClubUser", p, cab)
                try:
                    astron("addClubUserPlan", {"club_id": club, "user_id": email,
                                               "plan_id": plano, "update_if_exists": 0}, cab)
                except RuntimeError as e:
                    # quem já tem o plano não é erro
                    if "exist" not in str(e).lower() and "já" not in str(e).lower():
                        raise
                feitos[s["id"]] = {"form": form["nome"], "status": "ok",
                                   "em": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}
                novos += 1
                print(f"[ok] {form['nome']}: inscrição {s['id']} liberada")
            except Exception as e:
                erros += 1
                print(f"[erro] {form['nome']}: inscrição {s['id']}: {sem_dados(e)}")
            time.sleep(1)

    if not simular:
        json.dump(feitos, open(ARQ_FEITOS, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"Fim: {novos} liberados agora, {erros} com erro, {len(feitos)} no total.")
    if erros:
        sys.exit(1)


if __name__ == "__main__":
    main()
