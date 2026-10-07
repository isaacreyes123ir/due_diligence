# Due Diligence — Ecuador

Script de automatización para consultar datos públicos de entidades en Ecuador. Demuestra scraping con CAPTCHA (OCR), consumo de APIs gubernamentales y generación de reportes en Excel.

> **Estado**: proyecto de demostración y base extensible. No es para producción.

---

## Qué hace

Recibe un `RUC`, consulta:

1. **SRI** (`srienlinea.sri.gob.ec`) — datos de la empresa y representantes legales.
2. **Función Judicial** — demandas judiciales de la empresa y representante legal (como Actor y Demandado).
3. **SENESCYT** (`titulos-edusuperior.minedec.gob.ec`) — títulos académicos de los representantes (resuelve CAPTCHA con Tesseract OCR).

Genera un archivo `Reporte_{RUC}.xlsx` con los resultados.

---

## Instalación rápida

```bash
pip install -r requirements.txt
```

Requisitos externos:
- Python 3.10+
- Tesseract OCR instalado en el sistema operativo:
  - **Linux (Debian/Ubuntu):** `sudo apt install tesseract-ocr`
  - **Windows:** Descargar el instalador y configurar `RUTA_TESSERACT_WINDOWS` en `.env`.
---

## Configuración

Copiá el ejemplo:

```bash
cp .env.example .env
```

Editá `.env` con las URLs correspondientes (ya vienen las oficiales por defecto):

```env
SENESCYT_DOMINIO=https://titulos-edusuperior.minedec.gob.ec
SRI_API_URL=https://srienlinea.sri.gob.ec/...
JUDICIAL_API_URL=https://api.funcionjudicial.gob.ec/...
```

---

## Uso básico

```bash
python due_diligence.py
```

Te pedirá el RUC y mostrará los resultados en terminal, luego genera el Excel.

---

## Estructura del código

| Archivo / Función | Propósito |
|-------------------|-----------|
| `procesar_y_leer_captcha()` | Pre-procesa imagen (contraste) y extrae texto con `pytesseract`. Reutilizable para cualquier CAPTCHA alfanumérico. |
| `consultar_senescyt()` | Scraping completo de SENESCYT: obtiene cookie de sesión, descarga CAPTCHA, envía POST con `ViewState`, parsea tablas. |
| `consultar_sri()` | Llama a la API REST del SRI y retorna datos de empresa + representantes. |
| `consultar_demandas()` | POST a la API judicial por rol (`Actor` / `Demandado`). |
| `ejecutar_pipeline()` | Orquesta todo y exporta a `.xlsx` con `pandas` + `openpyxl`. |

---

## Dependencias

Ver `requirements.txt`:

- `requests` — HTTP
- `beautifulsoup4` — parsing HTML
- `pytesseract` + `Pillow` — OCR
- `pandas` + `openpyxl` — exportación Excel
- `rich` — tablas en terminal
- `python-dotenv` — variables de entorno

---

## Autor / Contexto

Script creado como demostración técnica: scraping con CAPTCHA, consumo de APIs públicas, orquestación con Python puro, generación de reportes.
