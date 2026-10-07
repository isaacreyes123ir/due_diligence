import os
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
import pytesseract
from PIL import Image, ImageEnhance, ImageOps
from rich.console import Console
from rich.table import Table
import urllib3
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
console = Console()

# Configurar ruta de Tesseract para usuarios de Windows
ruta_tesseract = os.getenv("RUTA_TESSERACT_WINDOWS")
if ruta_tesseract and os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = ruta_tesseract

# =====================================================================
# 1. MÓDULO SENESCYT
# =====================================================================
def procesar_y_leer_captcha(ruta_imagen: str) -> str:
    """Pre-procesa la imagen y extrae el texto usando Tesseract OCR"""
    try:
        img = Image.open(ruta_imagen)
        img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(3.0)
        
        config_ocr = '--psm 8 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -c user_defined_dpi=70'
        texto_captcha = pytesseract.image_to_string(img, config=config_ocr).strip()
        texto_captcha = texto_captcha.replace(" ", "").replace("\n", "")
        
        if len(texto_captcha) > 4:
            texto_captcha = texto_captcha[:4]
            
        return texto_captcha
    except Exception as e:
        console.print(f"[red][LOG OCR] Error en motor OCR: {e}[/red]")
        return ""

def consultar_senescyt(cedula: str, max_intentos=5):
    dominio = os.getenv("SENESCYT_DOMINIO")
    url_base = f"{dominio}/consulta-titulos-web/faces/vista/consulta/consulta.xhtml"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9"
    }
    titulos_encontrados = []

    for intento in range(1, max_intentos + 1):
        console.print(f"[cyan][LOG Senescyt] Intento {intento}/{max_intentos} para {cedula}...[/cyan]")
        sesion = requests.Session()
        
        try:
            res_get = sesion.get(url_base, headers=headers, timeout=15, verify=False)
            soup = BeautifulSoup(res_get.text, 'html.parser')
            
            view_state_tag = soup.find("input", {"name": "javax.faces.ViewState"})
            captcha_img_tag = soup.find("img", {"id": "formPrincipal:capimg"})
            
            if not view_state_tag or not captcha_img_tag:
                console.print("[yellow][LOG Senescyt] Error de conexión. Reintentando...[/yellow]")
                continue
                
            view_state = view_state_tag["value"]
            src = captcha_img_tag["src"]
            
            if "../" in src:
                url_captcha = f"{dominio}/consulta-titulos-web/Captcha.jpg"
            else:
                url_captcha = dominio + src
            
            res_captcha = sesion.get(url_captcha, headers=headers, verify=False)
            with open("captcha_temp.jpg", "wb") as f:
                f.write(res_captcha.content)
            
            texto_captcha = procesar_y_leer_captcha("captcha_temp.jpg")
            console.print(f"[cyan][LOG Senescyt] OCR detectó: '{texto_captcha}'[/cyan]")
            
            if len(texto_captcha) < 3:
                console.print("[yellow][LOG Senescyt] Captcha muy corto, reintentando...[/yellow]")
                continue

            payload = {
                "formPrincipal": "formPrincipal",
                "formPrincipal:apellidos": "", 
                "formPrincipal:identificacion": cedula,
                "formPrincipal:captchaSellerInput": texto_captcha,
                "formPrincipal:boton-buscar": "", 
                "javax.faces.ViewState": view_state
            }

            res_post = sesion.post(url_base, data=payload, headers=headers, timeout=20, verify=False)
            
            if "caracteres" in res_post.text.lower() and "incorrectos" in res_post.text.lower():
                console.print("[yellow][LOG Senescyt] El servidor rechazó el Captcha. Reintentando...[/yellow]")
                continue
            
            soup_post = BeautifulSoup(res_post.text, 'html.parser')
            tablas_encontradas = soup_post.find_all("tbody", id=lambda x: x and x.endswith('tablaAplicaciones_data'))
            
            if not tablas_encontradas:
                 if "No se ha encontrado información" in res_post.text:
                     console.print("[cyan][LOG Senescyt] La cédula no registra títulos universitarios.[/cyan]")
                 else:
                     console.print("[yellow][LOG Senescyt] No se encontraron tablas de resultados.[/yellow]")
                 break 
                 
            console.print(f"[green][LOG Senescyt] ¡ÉXITO! Tablas de títulos halladas.[/green]")
            
            for tabla in tablas_encontradas:
                etiqueta_nivel = tabla.find_previous("h4", class_="panel-title")
                nivel_texto = etiqueta_nivel.text.strip() if etiqueta_nivel else "Desconocido"
                
                if "tercer" in nivel_texto.lower():
                    nivel_limpio = "Tercer Nivel"
                elif "cuarto" in nivel_texto.lower() or "posgrado" in nivel_texto.lower():
                    nivel_limpio = "Cuarto Nivel"
                elif "tecnológico" in nivel_texto.lower() or "técnico" in nivel_texto.lower():
                    nivel_limpio = "Técnico / Tecnológico"
                else:
                    nivel_limpio = nivel_texto

                filas = tabla.find_all("tr")
                for fila in filas:
                    columnas = fila.find_all("td")
                    if len(columnas) >= 7:
                        titulos_encontrados.append({
                            "Cedula": cedula,
                            "Nivel": nivel_limpio,
                            "Titulo": columnas[0].text.strip(),
                            "Universidad": columnas[1].text.strip(),
                            "Fecha_Registro": columnas[5].text.strip()
                        })
            break
            
        except Exception as e:
            console.print(f"[red][LOG Senescyt] Fallo en el intento {intento}: {e}[/red]")
            time.sleep(1)
            
    if os.path.exists("captcha_temp.jpg"):
        os.remove("captcha_temp.jpg")
    return titulos_encontrados
        
# =====================================================================
# 2. MÓDULO SRI
# =====================================================================
def consultar_sri(ruc):
    sesion = requests.Session()
    headers_sri = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-419,es;q=0.8",
        "Connection": "keep-alive",
        "Content-Type": "application/json; charset=utf-8",
        "Referer": "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Sec-GPC": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
        "sec-ch-ua": "\"Chromium\";v=\"154\", \"Brave\";v=\"154\", \"Not A(Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\""
    }
    
    try:
        sesion.get("https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc", headers=headers_sri, timeout=10)
        
        url_api_base = os.getenv("SRI_API_URL")
        url_api = f"{url_api_base}?&ruc={ruc}"
        
        res = sesion.get(url_api, headers=headers_sri, timeout=10)
        
        if res.status_code == 200:
            datos = res.json()
            if "contribuyentes" in datos and len(datos["contribuyentes"]) > 0:
                empresa = datos["contribuyentes"][0]
                return {
                    "RUC": ruc,
                    "Razon_Social": empresa.get("razonSocial", ""),
                    "Estado": empresa.get("estadoContribuyenteRuc", ""),
                    "Actividad": empresa.get("actividadEconomicaPrincipal", ""),
                    "Representantes": empresa.get("representantesLegales", [])
                }
        else:
             console.print(f"[yellow][LOG SRI] Código HTTP inesperado: {res.status_code}[/yellow]")
    except Exception as e:
        console.print(f"[red][LOG SRI] Error consultando SRI: {e}[/red]")
    return None

# =====================================================================
# 3. MÓDULO DEMANDAS JUDICIALES
# =====================================================================
def consultar_demandas(identificacion, es_ruc=False):
    url_base = os.getenv("JUDICIAL_API_URL")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://procesosjudiciales.funcionjudicial.gob.ec",
        "Referer": "https://procesosjudiciales.funcionjudicial.gob.ec/",
        "Connection": "close"
    }
    todas_demandas = []
    roles = ["Actor", "Demandado"]
    
    for rol in roles:
        console.print(f"[cyan][LOG Demandas] Consultando {identificacion} como {rol}...[/cyan]")
        payload = {
            "numeroCausa": "",
            "actor": {"cedulaActor": identificacion if rol == "Actor" else "", "nombreActor": ""},
            "demandado": {"cedulaDemandado": identificacion if rol == "Demandado" else "", "nombreDemandado": ""},
            "provincia": "", "canton": "", "judicatura": "", "anio": ""
        }

        try:
            res = requests.post(url_base, json=payload, headers=headers, timeout=20, verify=False)
            if res.status_code == 200:
                datos = res.json()
                
                if isinstance(datos, list) and len(datos) > 0:
                    console.print(f"[green]  -> Éxito: {len(datos)} registros extraídos directamente.[/green]")
                    for d in datos:
                        todas_demandas.append({
                            "Identificacion": identificacion,
                            "Rol_en_juicio": rol,
                            "ID_Juicio": d.get('idJuicio', ''),
                            "Estado": d.get('estadoActual', ''),
                            "Delito_Materia": d.get('nombreDelito', '') or d.get('nombreMateria', ''),
                            "Fecha_Ingreso": d.get('fechaIngreso', '')
                        })
                else:
                    console.print(f"[yellow]  -> Sin registros como {rol}.[/yellow]")
            else:
                console.print(f"[red]  [!] Error del servidor: HTTP {res.status_code}[/red]")
        except Exception as e:
            console.print(f"[red]  [!] Error de conexión: {e}[/red]")
                
    return todas_demandas

# =====================================================================
# 4. ORQUESTADOR PRINCIPAL
# =====================================================================
def imprimir_tabla(titulo, df):
    if df.empty:
        console.print(f"[yellow]No se encontraron registros para: {titulo}[/yellow]")
        return
    
    table = Table(title=titulo, show_header=True, header_style="bold magenta")
    for col in df.columns:
        table.add_column(col)
    for _, row in df.iterrows():
        table.add_row(*[str(val) for val in row])
    console.print(table)
    print("\n")

def ejecutar_pipeline():
    console.print("[bold cyan]=== HERRAMIENTA DE DUE DILIGENCE ===[/bold cyan]")
    ruc = input("Ingrese el RUC a consultar: ").strip()
    
    datos_sri = consultar_sri(ruc)
        
    if not datos_sri:
        console.print("[bold red]No se pudo obtener información del RUC.[/bold red]")
        return

    empresas_data = [{"RUC": datos_sri["RUC"], "Razon_Social": datos_sri["Razon_Social"], "Estado": datos_sri["Estado"]}]
    representantes_data = []
    demandas_data = []
    titulos_data = []

    demandas_data.extend(consultar_demandas(ruc, es_ruc=True))

    for rep in datos_sri["Representantes"]:
        ced = rep.get("identificacion", "")
        nom = rep.get("nombre", "")
        representantes_data.append({"RUC_Empresa": ruc, "Cedula": ced, "Nombre": nom})
        
        demandas_data.extend(consultar_demandas(ced, es_ruc=False))
        titulos = consultar_senescyt(ced)
        titulos_data.extend(titulos)

    df_empresa = pd.DataFrame(empresas_data)
    df_reps = pd.DataFrame(representantes_data)
    df_demandas = pd.DataFrame(demandas_data)
    df_titulos = pd.DataFrame(titulos_data)

    console.print("\n[bold green]RESULTADOS OBTENIDOS[/bold green]")
    imprimir_tabla("DATOS DE LA EMPRESA", df_empresa)
    imprimir_tabla("REPRESENTANTES LEGALES", df_reps)
    imprimir_tabla("DEMANDAS JUDICIALES (EMPRESA Y REPRESENTANTES)", df_demandas)
    imprimir_tabla("TÍTULOS ACADÉMICOS (REPRESENTANTES)", df_titulos)

    archivo_excel = f"Reporte_{ruc}.xlsx"
    try:
        with pd.ExcelWriter(archivo_excel, engine='openpyxl') as writer:
            df_empresa.to_excel(writer, sheet_name='Empresa', index=False)
            df_reps.to_excel(writer, sheet_name='Representantes', index=False)
            if not df_demandas.empty:
                df_demandas.to_excel(writer, sheet_name='Demandas', index=False)
            if not df_titulos.empty:
                df_titulos.to_excel(writer, sheet_name='Titulos', index=False)
        console.print(f"[bold cyan]✅ Reporte Excel generado exitosamente: {archivo_excel}[/bold cyan]")
    except Exception as e:
        console.print(f"[red]Error al guardar el Excel: {e}[/red]")

if __name__ == "__main__":
    ejecutar_pipeline()
