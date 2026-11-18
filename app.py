import os
import json
import base64
import traceback
import unicodedata
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI(title="Painel Executivo de Gestão & SAC")

BASE_DIR = Path(__file__).resolve().parent
if (BASE_DIR / "static").is_dir():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# =========================================================================
# INÍCIO: inicializar_firestore
# =========================================================================
def inicializar_firestore():
    if not firebase_admin._apps:
        cred_env = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()
        if cred_env:
            cred_dict = json.loads(cred_env)
            if "private_key" in cred_dict and isinstance(cred_dict["private_key"], str):
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
        else:
            caminho_local = BASE_DIR / "firebase-credentials.json"
            if not caminho_local.is_file():
                raise RuntimeError(
                    "Credenciais do Firebase não encontradas. Configure a variável de ambiente "
                    "FIREBASE_CREDENTIALS_JSON no Render ou salve 'firebase-credentials.json' na raiz do projeto."
                )
            cred = credentials.Certificate(str(caminho_local))

        firebase_admin.initialize_app(cred, {"projectId": "chamadossac"})
    return firestore.client()


db = inicializar_firestore()
# =========================================================================
# TÉRMINO: inicializar_firestore
# =========================================================================


# =========================================================================
# INÍCIO: normalizar_utf8_seguro
# =========================================================================
def normalizar_utf8_seguro(valor: Any) -> str:
    """Repara dupla codificação UTF-8/Latin-1, sequências ï¿½ e restaura tokens com \\ufffd."""
    if valor is None:
        return ""
    if isinstance(valor, (bytes, bytearray)):
        try:
            texto = valor.decode("utf-8")
        except UnicodeDecodeError:
            texto = valor.decode("cp1252", errors="replace")
    else:
        texto = str(valor)

    if not texto:
        return ""

    # 1. Repara dupla codificação (Latin-1/CP1252 -> UTF-8)
    for _ in range(2):
        if any(marcador in texto for marcador in ("\u00c3", "\u00c2", "\u00e2\u20ac")):
            try:
                reparado = texto.encode("cp1252").decode("utf-8")
                if reparado and reparado != texto:
                    texto = reparado
                else:
                    break
            except Exception:
                try:
                    reparado = texto.encode("latin-1").decode("utf-8")
                    if reparado and reparado != texto:
                        texto = reparado
                    else:
                        break
                except Exception:
                    break
        else:
            break

    # 2. Converte a sequência literal "ï¿½" (\u00ef\u00bf\u00bd) para o marcador padrão \ufffd
    U = "\ufffd"
    if "\u00ef\u00bf\u00bd" in texto:
        texto = texto.replace("\u00ef\u00bf\u00bd", U)

    # 3. Somente atua se existir explicitamente o caractere de substituição \ufffd
    if U in texto:
        substituicoes_fffd = [
            (f"{U}{U}o", "ção"), (f"{U}{U}O", "ÇÃO"),
            (f"{U}{U}es", "ções"), (f"{U}{U}ES", "ÇÕES"),
            (f"{U}{U}a", "ça"), (f"{U}{U}A", "ÇA"),
            (f"S{U}o ", "São "), (f"S{U}O ", "SÃO "),
            (f"Ribeir{U}o", "Ribeirão"), (f"RIBEIR{U}O", "RIBEIRÃO"),
            (f"Ja{U}", "Jaú"), (f"JA{U}", "JAÚ"),
            (f"Goi{U}nia", "Goiânia"), (f"Bras{U}lia", "Brasília"),
            (f"Cuiab{U}", "Cuiabá"), (f"Bel{U}m", "Belém"),
            (f"Macei{U}", "Maceió"), (f"Florian{U}polis", "Florianópolis"),
            (f"N{U}o", "Não"), (f"N{U}O", "NÃO"),
            (f"Caf{U}", "Café"), (f"CAF{U}", "CAFÉ"),
            (f"Cr{U}dito", "Crédito"), (f"D{U}bito", "Débito"),
            (f"Devolu{U}{U}o", "Devolução"), (f"Transa{U}{U}o", "Transação"),
            (f"Observa{U}{U}o", "Observação"), (f"Descri{U}{U}o", "Descrição"),
            (f"Manuten{U}{U}o", "Manutenção"), (f"Refeit{U}rio", "Refeitório"),
            (f"Recep{U}{U}o", "Recepção"), (f"F{U}brica", "Fábrica"),
            (f"M{U}quina", "Máquina"), (f"M{U}quinas", "Máquinas"),
            (f"Pr{U}dio", "Prédio"), (f"T{U}rreo", "Térreo"),
            (f"M{U}dio", "Médio"), (f"M{U}dia", "Média"),
            (f"Cart{U}o", "Cartão"), (f"cart{U}o", "cartão"),
            (f"Aleat{U}ria", "Aleatória"), (f"N{U}mero", "Número"),
            (f"Hor{U}rio", "Horário"), (f"Relat{U}rio", "Relatório"),
            (f"Usu{U}rio", "Usuário"), (f"Funcion{U}rio", "Funcionário"),
            (f"{U}gua", "Água"), (f"A{U}{U}car", "Açúcar"),
            (f"Ch{U}", "Chá"), (f"P{U}o", "Pão"),
            (f"Eug{U}nio", "Eugênio"), (f"EUG{U}NIO", "EUGÊNIO"),
            (f"Jo{U}o", "João"), (f"Jos{U}", "José"),
            (f"Ant{U}nio", "Antônio"), (f"S{U}rgio", "Sérgio"),
            (f"M{U}rcio", "Márcio"), (f"M{U}rcia", "Márcia"),
            (f"Andr{U}", "André"), (f"L{U}cia", "Lúcia"),
            (f"Patr{U}cia", "Patrícia"), (f"Cl{U}udia", "Cláudia"),
            (f"Fl{U}via", "Flávia"), (f"Vit{U}ria", "Vitória"),
            (f"Val{U}ria", "Valéria"), (f"Rog{U}rio", "Rogério"),
            (f"C{U}sar", "César"), (f"V{U}tor", "Vítor"),
            (f"N{U}", "Nº"), (f"n{U}", "nº"),
        ]
        for errado, certo in substituicoes_fffd:
            if errado in texto:
                texto = texto.replace(errado, certo)

        texto = texto.replace(f"{U}o ", "ão ").replace(f"{U}es ", "ões ")
        if texto.endswith(f"{U}o"):
            texto = texto[:-2] + "ão"
        if texto.endswith(f"{U}es"):
            texto = texto[:-3] + "ões"

    return unicodedata.normalize("NFC", texto)
# =========================================================================
# TÉRMINO: normalizar_utf8_seguro
# =========================================================================


# =========================================================================
# INÍCIO: obter_logo_base64
# =========================================================================
def obter_logo_base64():
    diretorios_busca = [BASE_DIR / "static", BASE_DIR / "static/img", BASE_DIR]
    nomes_alvo = [
        "Logotipo.png", "Logotipo.PNG", "logotipo.png", "logotipo.PNG",
        "LOGOTIPO.PNG", "logo.png", "logo.PNG"
    ]
    for pasta in diretorios_busca:
        for nome in nomes_alvo:
            caminho = pasta / nome
            if caminho.is_file():
                ext = caminho.suffix.lower().replace(".", "")
                mime = "jpeg" if ext in ["jpg", "jpeg"] else "png"
                with open(caminho, "rb") as f:
                    return f"data:image/{mime};base64,{base64.b64encode(f.read()).decode('utf-8')}"
    return ""
# =========================================================================
# TÉRMINO: obter_logo_base64
# =========================================================================


# =========================================================================
# INÍCIO: format_currency_br
# =========================================================================
def format_currency_br(val):
    try:
        n = float(val) if val is not None else 0.0
        return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"
# =========================================================================
# TÉRMINO: format_currency_br
# =========================================================================


# =========================================================================
# INÍCIO: parse_date_to_sql
# =========================================================================
def parse_date_to_sql(val: Any) -> Optional[str]:
    """Converte DD/MM/AAAA ou YYYY-MM-DD para YYYY-MM-DD."""
    if not val:
        return None
    s = str(val).strip()
    if not s or s.lower() in ["none", "null", "undefined"]:
        return None
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    partes = s.split("/")
    if len(partes) == 3 and len(partes[2]) == 4:
        return f"{partes[2]}-{partes[1].zfill(2)}-{partes[0].zfill(2)}"
    return None
# =========================================================================
# TÉRMINO: parse_date_to_sql
# =========================================================================


# =========================================================================
# INÍCIO: format_date_br
# =========================================================================
def format_date_br(val: Any) -> str:
    """Garante exibição DD/MM/AAAA para o frontend."""
    if not val:
        return ""
    s = str(val).strip()
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s
# =========================================================================
# TÉRMINO: format_date_br
# =========================================================================


# =========================================================================
# INÍCIO: parse_float_sql
# =========================================================================
def parse_float_sql(val: Any) -> float:
    """Converte strings com R$, vírgulas e pontos para float seguro."""
    if val is None:
        return 0.0
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).replace("R$", "").strip()
        if not s:
            return 0.0
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0
# =========================================================================
# TÉRMINO: parse_float_sql
# =========================================================================


# =========================================================================
# INÍCIO: buscar_valores_colecao_firestore
# =========================================================================
def buscar_valores_colecao_firestore(nome_colecao: str, chaves_preferenciais: List[str]) -> List[str]:
    """Lê valores únicos de uma coleção auxiliar no Firestore (produtos, problemas, formas_pgt)."""
    valores = set()
    try:
        for doc in db.collection(nome_colecao).stream():
            dados = doc.to_dict() or {}
            encontrado = None
            for chave in chaves_preferenciais:
                if chave in dados and str(dados[chave]).strip():
                    encontrado = dados[chave]
                    break
            if not encontrado:
                for k, v in dados.items():
                    if k.lower() != "id" and isinstance(v, str) and v.strip():
                        encontrado = v
                        break
            if encontrado:
                valores.add(normalizar_utf8_seguro(encontrado).strip())
    except Exception:
        pass
    return sorted(list(valores))
# =========================================================================
# TÉRMINO: buscar_valores_colecao_firestore
# =========================================================================


# =========================================================================
# INÍCIO: sanitizar_estrutura_utf8
# =========================================================================
def sanitizar_estrutura_utf8(dado: Any) -> Any:
    """Aplica normalizar_utf8_seguro recursivamente em dicionários, listas e strings."""
    if isinstance(dado, str):
        return normalizar_utf8_seguro(dado)
    if isinstance(dado, list):
        return [sanitizar_estrutura_utf8(item) for item in dado]
    if isinstance(dado, dict):
        return {
            normalizar_utf8_seguro(k) if isinstance(k, str) else k: sanitizar_estrutura_utf8(v)
            for k, v in dado.items()
        }
    return dado
# =========================================================================
# TÉRMINO: sanitizar_estrutura_utf8
# =========================================================================


# =========================================================================
# INÍCIO: carregar_pagina_principal
# =========================================================================
@app.get("/", response_class=HTMLResponse)
async def carregar_pagina_principal(request: Request):
    logo_base64_src = obter_logo_base64()

    try:
        # 1. Usuários
        usuarios = []
        for doc in db.collection("usuarios").stream():
            u = doc.to_dict() or {}
            usuarios.append(sanitizar_estrutura_utf8({
                "id": doc.id,
                "nome": u.get("nome", ""),
                "usuario": u.get("usuario", ""),
                "senha": str(u.get("senha", "")),
                "acesso": u.get("acesso", "Atendente")
            }))
        usuarios.sort(key=lambda x: x.get("nome", "").lower())

        # 2. Clientes
        lista_clientes = []
        for doc in db.collection("clientes").stream():
            c = doc.to_dict() or {}
            lista_clientes.append(sanitizar_estrutura_utf8({
                "linha": doc.id,
                "id": doc.id,
                "cliente": c.get("cliente", ""),
                "local": c.get("local", ""),
                "localInterno": c.get("local_interno") or c.get("localInterno") or "",
                "maquina": c.get("maquina", ""),
                "modeloMaquina": c.get("modelo_maquina") or c.get("modeloMaquina") or "",
                "filialResponsavel": c.get("filial_responsavel") or c.get("filialResponsavel") or ""
            }))
        lista_clientes.sort(key=lambda x: x.get("cliente", "").lower())

        # 3. Listas dinâmicas das coleções auxiliares
        descricoes = buscar_valores_colecao_firestore("produtos", ["descricao", "produto", "nome", "item"])
        problemas = buscar_valores_colecao_firestore("problemas", ["problema", "descricao", "nome", "motivo"])
        formas_pgto = buscar_valores_colecao_firestore("formas_pgt", ["forma_pgt", "forma", "descricao", "nome"])

        # 4. Chamados
        chamados_raw = []
        for doc in db.collection("chamados").stream():
            ch = doc.to_dict() or {}
            chamados_raw.append({
                "linha": doc.id,
                "id": doc.id,
                "chamado": ch.get("chamado", ""),
                "data": format_date_br(ch.get("data", "")),
                "data_iso": parse_date_to_sql(ch.get("data", "")) or "",
                "cliente": ch.get("cliente", ""),
                "localInterno": ch.get("local_interno") or ch.get("localInterno") or "",
                "cidade": ch.get("cidade", ""),
                "descricao": ch.get("descricao", ""),
                "produto": ch.get("produto", ""),
                "dataTransacao": format_date_br(ch.get("data_transacao") or ch.get("dataTransacao") or ""),
                "horaTransacao": str(ch.get("hora_transacao") or ch.get("horaTransacao") or ""),
                "valor": ch.get("valor", 0),
                "nomeSobrenome": ch.get("nome_sobrenome") or ch.get("nomeSobrenome") or "",
                "celular": ch.get("celular", ""),
                "problemas": ch.get("problemas", ""),
                "formaPgto": ch.get("forma_pgto") or ch.get("formaPgto") or "",
                "reembolso": ch.get("reembolso", ""),
                "pix": ch.get("pix", ""),
                "atendente": ch.get("atendente", ""),
                "dataHoraLancamento": ch.get("data_hora_lancamento") or ch.get("dataHoraLancamento") or "",
                "reembolsoRealizado": ch.get("reembolso_realizado") or ch.get("reembolsoRealizado") or "Não",
                "financeiroResponsavel": ch.get("financeiro_responsavel") or ch.get("financeiroResponsavel") or "",
                "observacao": ch.get("observacao", "")
            })

        # Ordena chamados do mais recente para o mais antigo (data_iso desc, chamado desc)
        chamados_raw.sort(key=lambda x: (x.get("data_iso", ""), x.get("chamado", "")), reverse=True)

        if not descricoes:
            descricoes = sorted(list(set([normalizar_utf8_seguro(c.get("descricao", "")).strip() for c in chamados_raw if str(c.get("descricao", "")).strip()])))
        if not problemas:
            problemas = sorted(list(set([normalizar_utf8_seguro(c.get("problemas", "")).strip() for c in chamados_raw if str(c.get("problemas", "")).strip()])))
        if not formas_pgto:
            formas_pgto = sorted(list(set([normalizar_utf8_seguro(c.get("formaPgto", "")).strip() for c in chamados_raw if str(c.get("formaPgto", "")).strip()])))

        maior_sac_ano = {}
        chamados_formatados = []
        for c in chamados_raw:
            item = sanitizar_estrutura_utf8(dict(c))
            item.pop("data_iso", None)
            item["valor"] = format_currency_br(parse_float_sql(item.get("valor", 0)))
            chamados_formatados.append(item)

            ch_str = str(item.get("chamado", ""))
            if ch_str.startswith("SAC-"):
                partes = ch_str.split("-")
                if len(partes) == 3 and partes[2].isdigit():
                    ano, seq = partes[1], int(partes[2])
                    maior_sac_ano[ano] = max(maior_sac_ano.get(ano, 0), seq)

        cidades = sorted(list(set([c["filialResponsavel"] for c in lista_clientes if c.get("filialResponsavel")])))

        dados_sac = sanitizar_estrutura_utf8({
            "clientes": [{"cliente": c.get("cliente", ""), "local": c.get("localInterno", ""), "cidade": c.get("filialResponsavel", "")} for c in lista_clientes],
            "cadastro_clientes": lista_clientes,
            "formas_pagamento": sorted(list(set(formas_pgto))),
            "formas_pgt": sorted(list(set(formas_pgto))),
            "produtos": sorted(list(set(descricoes))),
            "descricoes": sorted(list(set(descricoes))),
            "problemas": sorted(list(set(problemas))),
            "cidades": cidades,
            "usuarios": usuarios,
            "maior_sac_ano": maior_sac_ano,
            "chamados": chamados_formatados
        })
        dados_sac_json_str = json.dumps(dados_sac, default=str, ensure_ascii=False)
        dados_sac_b64 = base64.b64encode(dados_sac_json_str.encode("utf-8")).decode("ascii")
        total_chamados = len(chamados_formatados)

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "logo_base64_src": logo_base64_src,
                "dados_sac_json": dados_sac_json_str,
                "dados_sac_b64": dados_sac_b64,
                "total_chamados_carregados": total_chamados
            },
            media_type="text/html; charset=utf-8"
        )

    except Exception:
        tb = traceback.format_exc()
        return HTMLResponse(
            content=f"""
            <div style="font-family: monospace; padding: 2rem; background: #0f172a; color: #f87171; min-height: 100vh;">
                <h2 style="color: #ef4444; margin-top: 0;">Traceback do Erro:</h2>
                <pre style="white-space: pre-wrap; word-break: break-all; font-size: 13px; line-height: 1.5;">{tb}</pre>
            </div>
            """,
            status_code=500,
            media_type="text/html; charset=utf-8"
        )
# =========================================================================
# TÉRMINO: carregar_pagina_principal
# =========================================================================


# =========================================================================
# INÍCIO: processar_acao_api
# =========================================================================
@app.post("/api/action")
async def processar_acao_api(request: Request):
    raw_bytes = await request.body()
    try:
        payload_bruto = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
    except UnicodeDecodeError:
        payload_bruto = json.loads(raw_bytes.decode("latin-1"))

    payload: Dict[str, Any] = sanitizar_estrutura_utf8(payload_bruto)
    acao = (payload.get("acao") or payload.get("action") or payload.get("tipo") or "").lower().strip()

    try:
        # =========================================================================
        # 1. INSERIR OU EDITAR NA COLEÇÃO chamados
        # =========================================================================
        if acao in ["inserir", "editar"]:
            chamado_num = normalizar_utf8_seguro(payload.get("Chamado") or payload.get("chamado") or "").strip()
            if not chamado_num:
                raise ValueError("O número do chamado é obrigatório.")

            data_sql = parse_date_to_sql(payload.get("Data") or payload.get("data")) or datetime.now().strftime("%Y-%m-%d")
            dt_transacao_sql = parse_date_to_sql(payload.get("Data da Transação") or payload.get("data_transacao") or payload.get("dataTransacao")) or ""

            hr_tr = payload.get("Hora da Transação") or payload.get("hora_transacao") or payload.get("horaTransacao")
            hr_tr_sql = str(hr_tr).strip() if hr_tr and str(hr_tr).strip() else ""

            valor_sql = parse_float_sql(payload.get("Valor") if "Valor" in payload else payload.get("valor", 0))

            dados_canonicos = {
                "chamado": chamado_num,
                "data": data_sql,
                "cliente": normalizar_utf8_seguro(payload.get("Cliente") or payload.get("cliente") or "").strip(),
                "local_interno": normalizar_utf8_seguro(payload.get("Local Interno") or payload.get("local_interno") or payload.get("localInterno") or "").strip(),
                "cidade": normalizar_utf8_seguro(payload.get("Cidade") or payload.get("cidade") or "").strip(),
                "descricao": normalizar_utf8_seguro(payload.get("Descrição") or payload.get("descricao") or "").strip(),
                "produto": normalizar_utf8_seguro(payload.get("Produto") or payload.get("produto") or "").strip(),
                "data_transacao": dt_transacao_sql,
                "hora_transacao": hr_tr_sql,
                "valor": valor_sql,
                "nome_sobrenome": normalizar_utf8_seguro(payload.get("Nome/Sobrenome") or payload.get("Nome Sobrenome") or payload.get("nome_sobrenome") or "").strip(),
                "celular": normalizar_utf8_seguro(payload.get("Celular") or payload.get("celular") or "").strip(),
                "problemas": normalizar_utf8_seguro(payload.get("Problemas") or payload.get("problemas") or "").strip(),
                "forma_pgto": normalizar_utf8_seguro(payload.get("Forma de Pagamento") or payload.get("forma_pgto") or payload.get("formaPgto") or "").strip(),
                "reembolso": normalizar_utf8_seguro(payload.get("Reembolso") or payload.get("reembolso") or "").strip(),
                "pix": normalizar_utf8_seguro(payload.get("Pix - Reembolso") or payload.get("pix") or "").strip(),
                "atendente": normalizar_utf8_seguro(payload.get("Atendente") or payload.get("atendente") or "").strip(),
                "data_hora_lancamento": normalizar_utf8_seguro(payload.get("Data/Hora do lançamento") or payload.get("data_hora_lancamento") or datetime.now().strftime("%d/%m/%Y %H:%M:%S")).strip(),
                "reembolso_realizado": normalizar_utf8_seguro(payload.get("Reembolso Realizado") or payload.get("reembolso_realizado") or "Não").strip(),
                "financeiro_responsavel": normalizar_utf8_seguro(payload.get("Financeiro Responsavel") or payload.get("financeiro_responsavel") or "").strip(),
                "observacao": normalizar_utf8_seguro(payload.get("Observação") or payload.get("observacao") or "").strip()
            }

            existentes = list(db.collection("chamados").where("chamado", "==", chamado_num).limit(1).stream())
            if acao == "inserir" and not existentes:
                _, doc_ref = db.collection("chamados").add(dados_canonicos)
                doc_id = doc_ref.id
            else:
                doc_id = str(payload.get("linha") or payload.get("id") or "").strip()
                if not doc_id and existentes:
                    doc_id = existentes[0].id

                if doc_id:
                    db.collection("chamados").document(doc_id).set(dados_canonicos, merge=True)
                else:
                    _, doc_ref = db.collection("chamados").add(dados_canonicos)
                    doc_id = doc_ref.id

            return JSONResponse(
                content={"status": "success", "id": doc_id, "message": f"Chamado {chamado_num} gravado com sucesso no Firebase."},
                media_type="application/json; charset=utf-8"
            )

        # =========================================================================
        # 2. EXCLUIR NA COLEÇÃO chamados
        # =========================================================================
        elif acao in ["excluir", "excluir_sac"]:
            chamado_num = normalizar_utf8_seguro(payload.get("Chamado") or payload.get("chamado") or "").strip()
            doc_id = str(payload.get("linha") or payload.get("id") or "").strip()

            if doc_id:
                db.collection("chamados").document(doc_id).delete()
            elif chamado_num:
                docs = list(db.collection("chamados").where("chamado", "==", chamado_num).stream())
                for d in docs:
                    db.collection("chamados").document(d.id).delete()
            else:
                raise ValueError("Número ou ID do chamado ausente para exclusão.")

            return JSONResponse(
                content={"status": "success", "message": f"Chamado {chamado_num} removido com sucesso do Firebase."},
                media_type="application/json; charset=utf-8"
            )

        # =========================================================================
        # 3. CLIENTES
        # =========================================================================
        elif acao in ["inserir_cliente", "editar_cliente"]:
            cli = normalizar_utf8_seguro(payload.get("Cliente") or "").strip()
            loc = normalizar_utf8_seguro(payload.get("Local") or "").strip()
            loc_int = normalizar_utf8_seguro(payload.get("Local interno") or payload.get("local_interno") or "").strip()
            maq = normalizar_utf8_seguro(payload.get("Máquina") or payload.get("maquina") or "").strip()
            mod = normalizar_utf8_seguro(payload.get("Modelo de máquina") or payload.get("modelo_maquina") or "").strip()
            fil = normalizar_utf8_seguro(payload.get("Filial Responsavel") or payload.get("filial_responsavel") or "").strip()

            dados_cli = {
                "cliente": cli,
                "local": loc,
                "local_interno": loc_int,
                "maquina": maq,
                "modelo_maquina": mod,
                "filial_responsavel": fil
            }

            if acao == "inserir_cliente":
                _, doc_ref = db.collection("clientes").add(dados_cli)
                doc_id = doc_ref.id
            else:
                doc_id = str(payload.get("linha") or payload.get("id") or "").strip()
                if not doc_id:
                    raise ValueError("ID do cliente não informado para edição.")
                db.collection("clientes").document(doc_id).update(dados_cli)

            return JSONResponse(
                content={"status": "success", "id": doc_id, "message": "Cliente salvo com sucesso."},
                media_type="application/json; charset=utf-8"
            )

        elif acao == "excluir_cliente":
            doc_id = str(payload.get("linha") or payload.get("id") or "").strip()
            if doc_id:
                db.collection("clientes").document(doc_id).delete()
            else:
                cli_del = normalizar_utf8_seguro(payload.get("Cliente") or "").strip()
                loc_del = normalizar_utf8_seguro(payload.get("Local interno") or "").strip()
                docs = (
                    db.collection("clientes")
                    .where("cliente", "==", cli_del)
                    .where("local_interno", "==", loc_del)
                    .stream()
                )
                for d in docs:
                    db.collection("clientes").document(d.id).delete()

            return JSONResponse(
                content={"status": "success", "message": "Cliente excluído com sucesso."},
                media_type="application/json; charset=utf-8"
            )

        # =========================================================================
        # 4. USUÁRIOS (INSERIR, EDITAR, EXCLUIR)
        # =========================================================================
        elif acao in ["inserir_usuario", "editar_usuario"]:
            nome_usr = normalizar_utf8_seguro(payload.get("nome") or payload.get("Nome") or "").strip()
            login_usr = normalizar_utf8_seguro(payload.get("usuario") or payload.get("Usuario") or "").strip().lower()
            senha_usr = normalizar_utf8_seguro(payload.get("senha") or payload.get("Senha") or "").strip()
            acesso_usr = normalizar_utf8_seguro(payload.get("acesso") or payload.get("Acesso") or "Atendente").strip()

            if not nome_usr or not login_usr or not senha_usr:
                raise ValueError("Nome, usuário e senha numérica são obrigatórios.")
            if not senha_usr.isdigit():
                raise ValueError("A senha deve conter apenas números.")
            if acesso_usr not in ["Geral", "Atendente"]:
                acesso_usr = "Atendente"

            preposicoes = {"de", "da", "do", "das", "dos", "e"}
            partes_nome = nome_usr.split()
            nome_formatado = " ".join(
                p.lower() if (i > 0 and p.lower() in preposicoes) else p.capitalize()
                for i, p in enumerate(partes_nome)
            )

            if acao == "inserir_usuario":
                duplicados = list(db.collection("usuarios").where("usuario", "==", login_usr).limit(1).stream())
                if duplicados:
                    raise ValueError(f"O usuário '{login_usr}' já está cadastrado.")
                _, doc_ref = db.collection("usuarios").add({
                    "nome": nome_formatado,
                    "usuario": login_usr,
                    "senha": senha_usr,
                    "acesso": acesso_usr
                })
                doc_id = doc_ref.id
            else:
                doc_id = str(payload.get("id") or "").strip()
                usuario_original = normalizar_utf8_seguro(payload.get("usuarioOriginal") or login_usr).strip().lower()

                if not doc_id and usuario_original:
                    encontrados = list(db.collection("usuarios").where("usuario", "==", usuario_original).limit(1).stream())
                    if encontrados:
                        doc_id = encontrados[0].id

                if not doc_id:
                    raise ValueError("Usuário não localizado no Firebase para edição.")

                db.collection("usuarios").document(doc_id).update({
                    "nome": nome_formatado,
                    "usuario": login_usr,
                    "senha": senha_usr,
                    "acesso": acesso_usr
                })

            return JSONResponse(
                content={"status": "success", "id": doc_id, "message": f"Usuário '{login_usr}' salvo com sucesso."},
                media_type="application/json; charset=utf-8"
            )

        elif acao == "excluir_usuario":
            doc_id = str(payload.get("id") or "").strip()
            login_del = normalizar_utf8_seguro(payload.get("usuario") or "").strip().lower()

            if not doc_id and login_del:
                encontrados = list(db.collection("usuarios").where("usuario", "==", login_del).limit(1).stream())
                if encontrados:
                    doc_id = encontrados[0].id

            if not doc_id:
                raise ValueError("Identificador do usuário ausente para exclusão.")

            db.collection("usuarios").document(doc_id).delete()
            return JSONResponse(
                content={"status": "success", "message": f"Usuário '{login_del}' excluído com sucesso."},
                media_type="application/json; charset=utf-8"
            )

    except Exception as e:
        erro_formatado = traceback.format_exc()
        print(f"ERRO FIREBASE EM /api/action:\n{erro_formatado}")
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(
        content={"status": "ignored"},
        media_type="application/json; charset=utf-8"
    )
# =========================================================================
# TÉRMINO: processar_acao_api
# =========================================================================