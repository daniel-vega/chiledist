import glob
import json
import unicodedata
import pandas as pd

# 1. Normalizador de cadenas de texto
def normalizar(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("utf-8")
    return texto.strip().upper()

# 2. Diccionario de mapeo Nombre de Comuna -> Código CUT (5 dígitos)
MAPA_COMUNA_CUT = {
    "ARICA": "15101", "CAMARONES": "15102", "PUTRE": "15201", "GENERAL LAGOS": "15202",
    "IQUIQUE": "01101", "ALTO HOSPICIO": "01107", "POZO ALMONTE": "01401", "CAMINA": "01402", "COLCHANE": "01403", "HUARA": "01404", "PICA": "01405",
    "ANTOFAGASTA": "02101", "MEJILLONES": "02102", "SIERRA GORDA": "02103", "TALTAL": "02104", "CALAMA": "02201", "OLLAGUE": "02202", "SAN PEDRO DE ATACAMA": "02203", "TOCOPILLA": "02301", "MARIA ELENA": "02302",
    "COPIAPO": "03101", "CALDERA": "03102", "TIERRA AMARILLA": "03103", "CHANARAL": "03201", "DIEGO DE ALMAGRO": "03202", "VALLENAR": "03301", "ALTO DEL CARMEN": "03302", "FREIRINA": "03303", "HUASCO": "03304",
    "LA SERENA": "04101", "COQUIMBO": "04102", "ANDACOLLO": "04103", "LA HIGUERA": "04104", "PAIHUANO": "04105", "VICUNA": "04106", "ILLAPEL": "04201", "CANELA": "04202", "LOS VILOS": "04203", "SALAMANCA": "04204", "OVALLE": "04301", "COMBARBALA": "04302", "MONTE PATRIA": "04303", "PUNITAQUI": "04304", "RIO HURTADO": "04305",
    "VALPARAISO": "05101", "CASABLANCA": "05102", "CONCON": "05103", "JUAN FERNANDEZ": "05104", "PUCHUNCAVI": "05105", "QUINTERO": "05107", "VINA DEL MAR": "05109", "ISLA DE PASCUA": "05201", "LOS ANDES": "05301", "CALLE LARGA": "05302", "RINCONADA": "05303", "SAN ESTEBAN": "05304", "LA LIGUA": "05401", "CABILDO": "05402", "PAPUDO": "05403", "PETORCA": "05404", "ZAPALLAR": "05405", "QUILLOTA": "05501", "LA CALERA": "05502", "CALERA": "05502", "HIJUELAS": "05503", "LA CRUZ": "05504", "NOGALES": "05506", "SAN ANTONIO": "05601", "ALGARROBO": "05602", "CARTAGENA": "05603", "EL QUISCO": "05604", "EL TABO": "05605", "SANTO DOMINGO": "05606", "SAN FELIPE": "05701", "CATEMU": "05702", "LLAILLAY": "05703", "LLAY-LLAY": "05703", "PANQUEHUE": "05704", "PUTAENDO": "05705", "SANTA MARIA": "05706", "QUILPUE": "05801", "LIMACHE": "05802", "OLMUE": "05803", "VILLA ALEMANA": "05804",
    "RANCAGUA": "06101", "CODEGUA": "06102", "COINCO": "06103", "COLTAUCO": "06104", "DONIHUE": "06105", "GRANEROS": "06106", "LAS CABRAS": "06107", "MACHALI": "06108", "MALLOA": "06109", "MOSTAZAL": "06110", "OLIVAR": "06111", "PEUMO": "06112", "PICHIDEGUA": "06113", "QUINTA DE TILCOCO": "06114", "RENGO": "06115", "REQUINOA": "06116", "SAN VICENTE": "06117", "PICHILEMU": "06201", "LA ESTRELLA": "06202", "LITUECHE": "06203", "MARCHIHUE": "06204", "MARCHIGUE": "06204", "NAVIDAD": "06205", "PAREDONES": "06206", "SAN FERNANDO": "06301", "CHEPICA": "06302", "CHIMBARONGO": "06303", "LOLOL": "06304", "NANCAGUA": "06305", "PALMILLA": "06306", "PERALILLO": "06307", "PLACILLA": "06308", "PUMANQUE": "06309", "SANTA CRUZ": "06310",
    "TALCA": "07101", "CONSTITUCION": "07102", "CUREPTO": "07103", "EMPEDRADO": "07104", "MAULE": "07105", "PELARCO": "07106", "PENCAHUE": "07107", "RIO CLARO": "07108", "SAN CLEMENTE": "07109", "SAN RAFAEL": "07110", "CAUQUENES": "07201", "CHANCO": "07202", "PELLUHUE": "07203", "CURICO": "07301", "HUALANE": "07302", "LICANTEN": "07303", "MOLINA": "07304", "RAUCO": "07305", "ROMERAL": "07306", "SAGRADA FAMILIA": "07307", "TENO": "07308", "VICHUQUEN": "07309", "LINARES": "07401", "COLBUN": "07402", "LONGAVI": "07403", "PARRAL": "07404", "RETIRO": "07405", "SAN JAVIER": "07406", "VILLA ALEGRE": "07407", "YERBAS BUENAS": "07408",
    "CONCEPCION": "08101", "CORONEL": "08102", "CHIGUAYANTE": "08103", "FLORIDA": "08104", "HUALQUI": "08105", "LOTA": "08106", "PENCO": "08107", "SAN PEDRO DE LA PAZ": "08108", "SANTA JUANA": "08109", "TALCAHUANO": "08110", "TOME": "08111", "HUALPEN": "08112", "LEBU": "08201", "ARAUCO": "08202", "CANETE": "08203", "CONTULMO": "08204", "CURANILAHUE": "08205", "LOS ALAMOS": "08206", "TIRUA": "08207", "LOS ANGELES": "08301", "ANTUCO": "08302", "CABRERO": "08303", "LAJA": "08304", "MULCHEN": "08305", "NACIMIENTO": "08306", "NEGRETE": "08307", "QUILACO": "08308", "QUILLECO": "08309", "SAN ROSENDO": "08310", "SANTA BARBARA": "08311", "TUCAPEL": "08312", "YUMBEL": "08313", "ALTO BIOBIO": "08314",
    "TEMUCO": "09101", "CARAHUE": "09102", "CUNCO": "09103", "CURARREHUE": "09104", "GALVARINO": "09105", "FREIRE": "09106", "GORBEA": "09107", "LAUTARO": "09108", "LONCOCHE": "09109", "TOLTEN": "09110", "NUEVA IMPERIAL": "09111", "MELIPEUCO": "09112", "PADRE LAS CASAS": "09113", "PERQUENCO": "09114", "PITRUFQUEN": "09115", "PUCON": "09116", "SAAVEDRA": "09117", "TEODORO SCHMIDT": "09118", "VILCUN": "09119", "VILLARRICA": "09120", "CHOLCHOL": "09121", "ANGOL": "09201", "COLLIPULLI": "09202", "CURACAUTIN": "09203", "ERCILLA": "09204", "LONQUIMAY": "09205", "LOS SAUCES": "09206", "LUMACO": "09207", "PUREN": "09208", "RENAICO": "09209", "TRAIGUEN": "09210", "VICTORIA": "09211",
    "PUERTO MONTT": "10101", "CALBUCO": "10102", "FRESIA": "10103", "FRUTILLAR": "10104", "LOS MUERMOS": "10105", "LLANQUIHUE": "10106", "MAULLIN": "10107", "COCHAMO": "10108", "PUERTO VARAS": "10109", "CASTRO": "10201", "ANCUD": "10202", "CHONCHI": "10203", "CURACO DE VELEZ": "10204", "DALCAHUE": "10205", "PUQUELDON": "10206", "QUEILEN": "10207", "QUELLON": "10208", "QUEMCHI": "10209", "QUINCHAO": "10210", "OSORNO": "10301", "PUERTO OCTAY": "10302", "PURRANQUE": "10303", "PUYEHUE": "10304", "RIO NEGRO": "10305", "SAN JUAN DE LA COSTA": "10306", "SAN PABLO": "10307", "CHAITEN": "10401", "FUTALEUFU": "10402", "HUALAIHUE": "10403", "PALENA": "10404",
    "COIHAIQUE": "11101", "COYHAIQUE": "11101", "LAGO VERDE": "11102", "AYSEN": "11201", "PUERTO AYSEN": "11201", "CISNES": "11202", "GUAITECAS": "11203", "COCHRANE": "11301", "OHIGGINS": "11302", "O'HIGGINS": "11302", "TORTEL": "11303", "CHILE CHICO": "11401", "RIO IBANEZ": "11402",
    "PUNTA ARENAS": "12101", "LAGUNA BLANCA": "12102", "RIO VERDE": "12103", "SAN GREGORIO": "12104", "CABO DE HORNOS": "12201", "CABO DE HORNOS(NAVARINO)": "12201", "CABO DE HORNOS(EX-NAVARINO)": "12201", "CABO DE HORNOS (EX-NAVARINO)": "12201", "NAVARINO": "12201", "ANTARTICA": "12202", "PORVENIR": "12301", "PRIMAVERA": "12302", "TIMAUKEL": "12303", "NATALES": "12401", "TORRES DEL PAINE": "12402",
    "SANTIAGO": "13101", "CERRO NAVIA": "13102", "CONCHALI": "13103", "EL BOSQUE": "13104", "CERRILLOS": "13105", "ESTACION CENTRAL": "13106", "HUECHURABA": "13107", "INDEPENDENCIA": "13108", "LA CISTERNA": "13109", "LA FLORIDA": "13110", "LA GRANJA": "13111", "LA REINA": "13112", "LAS CONDES": "13113", "LO BARNECHEA": "13114", "LA PINTANA": "13115", "LO PRADO": "13116", "MACUL": "13117", "MAIPU": "13118", "LO ESPEJO": "13119", "NUNOA": "13120", "PEDRO AGUIRRE CERDA": "13121", "PENALOLEN": "13122", "PROVIDENCIA": "13123", "QUINTA NORMAL": "13124", "PUDAHUEL": "13125", "QUILICURA": "13126", "RECOLETA": "13127", "RENCA": "13128", "SAN JOAQUIN": "13129", "SAN MIGUEL": "13130", "SAN RAMON": "13131", "VITACURA": "13132", "PUENTE ALTO": "13201", "PIRQUE": "13202", "SAN JOSE DE MAIPO": "13203", "COLINA": "13301", "LAMPA": "13302", "TILTIL": "13303", "TIL TIL": "13303", "SAN BERNARDO": "13401", "BUIN": "13402", "CALERA DE TANGO": "13403", "PAINE": "13404", "MELIPILLA": "13501", "ALHUE": "13502", "CURACAVI": "13503", "MARIA PINTO": "13504", "SAN PEDRO": "13505", "TALAGANTE": "13601", "EL MONTE": "13602", "ISLA DE MAIPO": "13603", "PADRE HURTADO": "13604", "PENAFLOR": "13605",
    "VALDIVIA": "14101", "CORRAL": "14102", "LANCO": "14103", "LOS LAGOS": "14104", "MAFIL": "14105", "MARIQUINA": "14106", "PAILLACO": "14107", "PANGUIPULLI": "14108", "LA UNION": "14201", "FUTRONO": "14202", "LAGO RANCO": "14203", "RIO BUENO": "14204",
    "CHILLAN": "16101", "BULNES": "16102", "CHILLAN VIEJO": "16103", "EL CARMEN": "16104", "PEMUCO": "16105", "PINTO": "16106", "QUILLON": "16107", "SAN IGNACIO": "16108", "YUNGAY": "16109", "QUIRIHUE": "16201", "COBQUECURA": "16202", "COELEMU": "16203", "NINHUE": "16204", "PORTEZUELO": "16205", "RANQUIL": "16206", "TREHUACO": "16207", "TREGUACO": "16207", "SAN CARLOS": "16301", "COIHUECO": "16302", "NIQUEN": "16303", "SAN FABIAN": "16304", "SAN NICOLAS": "16305"
}

def procesar_archivos_servel(patron_archivos: str, output_csv: str = "servel_2025_por_cut.csv"):
    archivos = sorted(glob.glob(patron_archivos))
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos con el patrón: {patron_archivos}")
    
    lista_df = []
    for archivo in archivos:
        df = pd.read_excel(archivo, engine="openpyxl")
        # Homogeneizar nombres de columnas a minúsculas
        df.columns = [c.strip().lower() for c in df.columns]
        
        # Filtrar columnas requeridas
        df_sub = df[["comuna", "partido", "votos_preliminares"]].copy()
        lista_df.append(df_sub)
        
    df_total = pd.concat(lista_df, ignore_index=True)
    
    # Normalizar valores
    df_total["comuna_norm"] = df_total["comuna"].apply(normalizar)
    df_total["partido"] = df_total["partido"].fillna("IND").apply(normalizar)
    df_total["votos"] = pd.to_numeric(df_total["votos_preliminares"], errors="coerce").fillna(0).astype(int)
    
    # Asignar CUT
    df_total["CUT"] = df_total["comuna_norm"].map(MAPA_COMUNA_CUT)
    
    # Verificar si hubo alguna comuna no mapeada
    sin_cut = df_total[df_total["CUT"].isna()]["comuna"].unique()
    if len(sin_cut) > 0:
        print(f"Advertencia: Comunas no reconocidas en el mapeo: {sin_cut}")
        
    # Agrupación y suma matemática
    df_resultado = df_total.groupby(["CUT", "partido"], as_index=False)["votos"].sum()
    df_resultado = df_resultado[df_resultado["votos"] > 0]
    df_resultado.sort_values(by=["CUT", "partido"], inplace=True)
    
    # Exportar archivo final
    df_resultado.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Generado {output_csv} exitosamente con {len(df_resultado)} registros.")

if __name__ == "__main__":
    # Para procesar los 28 archivos de diputados:
    procesar_archivos_servel("PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx", "servel_2025_diputados_por_cut.csv")
    
    # Para procesar los 7 archivos de senadores:
    procesar_archivos_servel("PRELIMINARES_SENADORES_CIRCUNSCRIPCI*.xlsx", "servel_2025_senadores_por_cut.csv")
