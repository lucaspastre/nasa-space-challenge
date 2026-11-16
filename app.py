import os, io, json, time, hashlib, zipfile, duckdb, folium, numpy as np, pandas as pd, plotly.express as px, plotly.graph_objects as go
import xml.etree.ElementTree as ET
import shapely, streamlit as st
from shapely.geometry import shape, box, mapping
from folium.plugins import Draw
from streamlit_folium import st_folium
from branca.element import MacroElement
from jinja2 import Template

RES = 0.25
OV_START = "2018-04-01"
ANO_BASE = 2003                       # 1º ano completo com Terra + Aqua
DADOS_INI = pd.Timestamp("2000-11-01")
PTS = "data/proc/points.parquet" if os.path.exists("data/proc/points.parquet") else "data/proc/points/*.parquet"
BR_FILE = "data/proc/brasil.geojson" if os.path.exists("data/proc/brasil.geojson") else "data/raw/brasil.geojson"

# Paleta sequencial (mapa + calendário): YlOrRd (ColorBrewer) — segura para daltonismo e legível em cinza
PAL_NOME = "YlOrRd"
PAL = ["#fed976", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026"]

# Temas da interface
TEMAS = {
    "light": dict(bg="#F6F7F9", surface="#FFFFFF", border="#E3E6EA", text="#111827", text2="#374151",
                  muted="#6B7280", input="#FFFFFF", hover="#F3F4F6", grid="#E5E7EB", accent="#0B6B3F", gold="#D4A21A", accent_bg="#E8F3EC",
                  mask="#9CA3AF", mask_op=0.55, harm="#000000", leaflet_bg="#E5E7EB",
                  bar="#C7CDD4", destaque="#0072B2",
                  danger="#B42318", danger_bg="#FDECEA", success="#1E7F4F", success_bg="#E6F4EC"),
    "dark":  dict(bg="#0F1419", surface="#171D24", border="#2A323C", text="#E5E7EB", text2="#CBD2DA",
                  muted="#94A0AE", input="#1E252E", hover="#222A33", grid="#2A323C", accent="#4DB57F", gold="#E3B53C", accent_bg="#16281F",
                  mask="#000000", mask_op=0.45, harm="#E5E7EB", leaflet_bg="#1B2026",
                  bar="#4B5563", destaque="#56B4E9",
                  danger="#F07167", danger_bg="#2D1A1A", success="#4CC38A", success_bg="#15291F"),
}

# Camadas do mapa (sem chave de API)
LIGHT_LABELS = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
DARK_LABELS = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
LABELS_ATTR = "Tiles &copy; Esri — Esri, HERE, Garmin, &copy; OpenStreetMap contributors"
ESRI_IMG = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_ATTR = "Tiles &copy; Esri — Esri, Maxar, Earthstar Geographics"

SA = dict(min_lat=-60, max_lat=15, min_lon=-95, max_lon=-25)   # América do Sul (com margem)

# [estado] Unidades da Federação (código IBGE -> sigla, nome) e malha das UFs
UF = {11: ("RO", "Rondônia"), 12: ("AC", "Acre"), 13: ("AM", "Amazonas"), 14: ("RR", "Roraima"),
      15: ("PA", "Pará"), 16: ("AP", "Amapá"), 17: ("TO", "Tocantins"), 21: ("MA", "Maranhão"),
      22: ("PI", "Piauí"), 23: ("CE", "Ceará"), 24: ("RN", "Rio Grande do Norte"), 25: ("PB", "Paraíba"),
      26: ("PE", "Pernambuco"), 27: ("AL", "Alagoas"), 28: ("SE", "Sergipe"), 29: ("BA", "Bahia"),
      31: ("MG", "Minas Gerais"), 32: ("ES", "Espírito Santo"), 33: ("RJ", "Rio de Janeiro"),
      35: ("SP", "São Paulo"), 41: ("PR", "Paraná"), 42: ("SC", "Santa Catarina"),
      43: ("RS", "Rio Grande do Sul"), 50: ("MS", "Mato Grosso do Sul"), 51: ("MT", "Mato Grosso"),
      52: ("GO", "Goiás"), 53: ("DF", "Distrito Federal")}
UF_NOME = {s: n for s, n in UF.values()}
UF_FILE = "data/raw/estados.geojson"
UF_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
UF_PARAMS = {"formato": "application/vnd.geo+json", "qualidade": "intermediaria", "intrarregiao": "UF"}

# [tempo real] FIRMS NRT (API de área) e [alertas] histórico
FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{src}/{bbox}/{dias}"
NRT_SRC = {"VIIRS_NOAA20_NRT": "NOAA-20", "VIIRS_NOAA21_NRT": "NOAA-21", "VIIRS_SNPP_NRT": "S-NPP"}
BBOX_BR = "-74,-34,-28,6"                     # oeste, sul, leste, norte (inclui as ilhas oceânicas)
TZ_BR = "America/Sao_Paulo"
INTERVALOS = [5, 10, 15, 30, 60]              # minutos
ALERT_FILE = "data/alerts/alertas.csv"
HIST_COLS = ["alerta_id", "verificado_em", "area", "area_key", "id", "latitude", "longitude", "data_hora_utc",
             "satelite", "frp", "confianca", "daynight"]

# ---------------- textos (PT / EN)
TXT = {
"PT": dict(
    meses=["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
    config="Configurações", idioma="Idioma", tema="Tema", light="Claro", dark="Escuro",
    filtros="Filtros", area="Área de interesse",
    draw="Desenhar no mapa", coords="Coordenadas", estado="Estados",           # [estado]
    upload="Enviar arquivo", pais="País inteiro",                              # [upload] [país]
    uf_lbl="Estados", uf_ph="Escolha um ou mais estados",                      # [estado]
    uf_err="Não foi possível carregar os limites dos estados (IBGE). Salve um GeoJSON das UFs em "
           "data/raw/estados.geojson e recarregue a página.",
    pais_hint="Pinta a intensidade de focos em todo o Brasil e, na aba Tempo real, mostra todos os focos do "
              "país. Pode levar alguns segundos na primeira vez.",
    brasil="Brasil",
    # [várias áreas]
    area_lbl="Área: {a}", area_n_lbl="{n} áreas selecionadas",
    areas_titulo="Suas áreas (clique no nome para editar)", rm_area="Remover esta área", limpar_areas="Remover todas as áreas",
    nome_draw="Desenho", nome_coords="Polígono", nome_upload="Arquivo", concluir="Concluir área",
    fontes_hint="Marque uma ou mais formas de escolher áreas; dá para combiná-las (ex.: um arquivo e um desenho).",
    nome_area="Nome da área (opcional)", nome_lbl="Nome da área", fonte_off="Fonte desmarcada: áreas guardadas, mas fora da análise.",
    lat_min="Lat mín", lat_max="Lat máx", lon_min="Lon mín", lon_max="Lon máx",
    limpar="Limpar seleção",
    rm_btn="Remover área selecionada",                                         # [remover área]
    rm_tip="Clique na área para removê-la (Esc cancela)",                      # [remover área]
    rm_vazio="Nenhuma área para remover",                                      # [remover área]
    draw_hint="Desenhe polígonos ou retângulos com as ferramentas no canto superior esquerdo do mapa. "
              "Cada desenho vira uma área; dá para adicionar várias.",
    # [upload] envio do limite da área por arquivo
    up_lbl="Arquivo com o limite da área",
    up_hint="KML, KMZ, GeoJSON ou shapefile .zip (com .shp, .shx e .dbf), em graus de lat/lon "
            "(WGS84 ou SIRGAS 2000). Ex.: o perímetro do imóvel baixado do CAR/SICAR. "
            "Dá para enviar vários arquivos: cada um vira uma área (polígonos de um mesmo arquivo são unidos).",
    up_ler="Não foi possível ler o arquivo. Confira se é um KML, KMZ, GeoJSON ou shapefile .zip válido.",
    up_vazio="O arquivo não contém polígonos (só pontos ou linhas). Envie o contorno da área.",
    up_graus="As coordenadas do arquivo não estão em graus de latitude/longitude (podem estar em UTM). "
             "Exporte em WGS84 ou SIRGAS 2000 geográfico.",
    up_pyshp="Para ler shapefile, instale o pacote pyshp (pip install pyshp) ou envie o arquivo em KML/GeoJSON.",
    up_tipo="Formato não suportado. Use KML, KMZ, GeoJSON ou shapefile .zip.",
    err_lat="Coordenadas inválidas: a latitude mínima deve ser menor que a máxima.",
    err_lon="Coordenadas inválidas: a longitude mínima deve ser menor que a máxima.",
    err_fora="A área informada está fora da cobertura de dados (Brasil). Mostrando o Brasil inteiro.",
    lat="Latitude", lon="Longitude", add_pt="Adicionar ponto",
    pts_titulo="Pontos adicionados", rm_pt="Remover este ponto", limpar_pts="Limpar pontos",
    pt_fora="Ponto fora da área do mapa (América do Sul: lat −60 a 15, lon −95 a −25).",
    pt_dup="Esse ponto já foi adicionado.",
    pt_min="Adicione pelo menos 3 pontos ({n}/3) e clique em “Concluir área”. Os pontos são ligados na ordem em que foram adicionados. Repita para adicionar outras áreas.",
    poly_linha="Os pontos estão alinhados e não formam uma área. Adicione um ponto fora dessa linha.",
    poly_cruza="Os lados da área se cruzam. Remova pontos ou adicione-os em sequência, contornando a área.",
    periodo="Período", de="De", ate="Até", mes="Mês", ano="Ano",
    per_hint="As opções de “Até” começam no mês escolhido em “De”.",
    disp="Dados disponíveis: {a} – {b}.",
    err_periodo="O início era posterior ao fim; as datas foram invertidas.",
    ajuste="Período ajustado ao intervalo com dados.",
    aviso_2000="Em 2000–2002 só o satélite Terra operava; contagens subestimadas.",
    info="Informações", acess="Acessibilidade", sobre="Sobre os dados",
    acess_txt="""
Todas as cores foram escolhidas para serem distinguíveis por pessoas com daltonismo:
- **Mapa e calendário:** paleta *YlOrRd* (ColorBrewer), segura para daltonismo e legível em tons de cinza; do amarelo claro (menos focos) ao vermelho escuro (mais focos). No mapa, a cor aparece só dentro da área selecionada, com legenda abaixo.
- **Anomalia:** escala divergente *RdBu* (ColorBrewer): azul = abaixo da mediana, branco = normal, vermelho = acima.
- **Comparação anual:** ano em destaque em azul (*Okabe-Ito*), demais anos em cinza; mediana em linha tracejada vermelho-alaranjada e média em linha pontilhada verde, com os valores escritos ao lado do gráfico.
- **Gráficos de linha:** paleta *Okabe-Ito*, e cada série também tem um tipo de linha diferente.
- Os indicadores mostram sinal (+/−) e seta, não só cor.
- Temas claro e escuro disponíveis em ⚙ Configurações.
""",
    sobre_txt="""
- **Fonte:** NASA FIRMS — MODIS C6.1 (2000–2025) e VIIRS NOAA-20 375 m (2018–hoje).
- **Cobertura:** Brasil. Áreas em cinza no mapa estão fora da cobertura.
- **Unidade:** focos VIIRS-equivalentes.
- **Harmonização:** fator *k* por célula de 0,25°, calibrado na sobreposição abr/2018–dez/2025, com *shrinkage* para regiões de 2° e para o Brasil.
- Antes de abr/2018: *k* × MODIS. Depois: VIIRS NOAA-20.
""",
    resize_hint="↔ Arraste a borda direita deste painel para redimensioná-lo.",
    eyebrow="NASA Space Apps 2026 · Dados NASA FIRMS", titulo="Flama",
    sub="Calendário de Queimadas · Série harmonizada MODIS + VIIRS de focos de calor · Brasil",
    dados_ate="Dados até", area_coords="Área: coordenadas", area_poly="Área: polígono desenhado",
    area_up="Área: arquivo enviado",                                           # [upload]
    area_br="Área: Brasil inteiro",
    l_sat="Satélite", l_fora="Fora da cobertura", l_limite="Limite do Brasil",
    l_focos="Focos de calor", l_sel="Área selecionada", l_rot="Rótulos",
    gerando="Gerando mapa da área...", calculando="Calculando comparação do mês atual...",
    leg_titulo="Intensidade de focos por ano", menor="Menor", maior="Maior",
    leg_nota="Escala logarítmica, relativa à área exibida · paleta acessível",
    fora_cob="Fora da cobertura de dados",
    sel_hint="Selecione uma área de interesse (ou “País inteiro”) para visualizar a intensidade de focos no mapa. Indicadores e gráficos: Brasil inteiro.",
    sem_focos="Nenhum foco registrado nessa área.",
    kpi_total="Total de focos no período", kpi_vs="vs mediana", focos="focos",
    kpi_ano="Ano com mais focos", kpi_mes="Mês mais crítico (mediana)", kpi_cel="Células 0,25° selecionadas",
    kpi_temp="Temporada típica (pico)",                                        # [temporada]
    temp_help="Início: mês em que normalmente já se acumularam 10% dos focos do ano. Fim: mês em que se "
              "chega a 90%. Entre parênteses: o mês de pico.",
    unidade="Unidade: focos VIIRS-equivalentes (NOAA-20, 375 m).",
    nota_parcial="O mês atual ainda não terminou: o indicador compara os dias 1–{d} de {m} deste ano com a mediana do mesmo intervalo em {a0}–{a1}.",
    abas=["Calendário", "Anomalia", "Comparação anual", "Série temporal", "Validação", "Downloads",
          "Tempo real", "Alertas"],                                            # [tempo real] [alertas]
    # [tempo real]
    rt_sem_chave="Para o monitoramento em tempo real, configure a chave da API do FIRMS (MAP_KEY) em "
                 "`.streamlit/secrets.toml` (`FIRMS_KEY = \"...\"`) ou na variável de ambiente `FIRMS_KEY`. "
                 "A chave é gratuita: firms.modaps.eosdis.nasa.gov/api/map_key",
    rt_buscando="Consultando o FIRMS...",
    rt_status="Atualizado às {h} (horário de Brasília) · próxima atualização por volta das {p} · a cada {n} min",
    rt_agora="Atualizar agora",
    rt_total="Focos nas últimas 24 h", rt_area="Brasil inteiro (24 h)",
    rt_sem_area="Selecione uma área de interesse em Filtros (ou “País inteiro”) para ver os focos em tempo real dela.",
    rt_recente="Detecção mais recente", rt_frp="FRP máximo (MW)",
    rt_erro="Sem resposta do FIRMS para: {s}. Os dados mostrados podem estar incompletos.",
    rt_vazio="Nenhum foco nas últimas 24 h.", rt_horas="Horas atrás",
    rt_hover="Detecção: {h} (Brasília)<br>Satélite: {s}<br>FRP: {f} MW",
    rt_cap="Fonte: NASA FIRMS, VIIRS NRT (NOAA-20, NOAA-21 e S-NPP), confiança nominal ou alta, últimas 24 h, "
           "dentro da área de interesse. Cada passagem de satélite chega ao FIRMS cerca de 3 h depois. Cor mais escura = "
           "detecção mais recente. Os focos em tempo real não são harmonizados (contagem bruta).",
    rt_dl="Focos das últimas 24 h na área (CSV)",
    rt_intervalo="Atualização do tempo real",
    rt_int_help="De quanto em quanto tempo o app consulta o FIRMS. O FIRMS recebe dados novos a cada passagem "
                "de satélite, então intervalos menores que 10 min raramente trazem focos novos.",
    # [alertas]
    al_titulo="Alertas de incêndio", al_on="Receber alertas",
    al_hint="Os alertas monitoram as áreas de interesse escolhidas em Filtros (cada área separadamente).",
    al_toast="{n} novo(s) foco(s) em {a}",
    al_off="Os alertas estão desligados. Ative em ⚙ Configurações → Alertas de incêndio.",
    al_status="Monitorando: {a} · verificação a cada {n} min. Um alerta é gerado quando aparece um foco "
              "novo (VIIRS NRT) dentro da área.",
    al_sem_area="Nenhuma área de interesse selecionada. Escolha uma ou mais em Filtros → Área de interesse.",
    al_sem_chave="Os alertas dependem da chave da API do FIRMS (veja a aba Tempo real).",
    al_vazio="Nenhum alerta registrado ainda.",
    al_ultimos="Últimos alertas",
    al_cols=dict(quando="Verificado em (Brasília)", area="Área", focos="Focos novos",
                 frp="FRP máx. (MW)", ultima="Última detecção (UTC)"),
    al_dl="Focos dos alertas (CSV)", al_dl_res="Resumo dos alertas (CSV)",
    al_limpar="Limpar histórico", al_limpar_conf="Apaga todos os alertas salvos. Não dá para desfazer.",
    # [info] explicações dos indicadores (ícone ⓘ)
    h_total="Soma dos focos de calor na área e no período escolhidos em Filtros, já harmonizados "
            "(VIIRS-equivalentes): antes de abr/2018 vêm do MODIS multiplicado pelo fator k; depois, do VIIRS NOAA-20.",
    h_vs="Focos do mês atual, do dia 1 até o último dia com dados, comparados com a mediana do mesmo intervalo "
         "de dias nos anos anteriores (desde 2003). Vermelho com seta para cima = acima do normal; verde com seta "
         "para baixo = abaixo.",
    h_ano="Ano com a maior soma de focos na área, dentro do período escolhido.",
    h_cel="Quantidade de células da grade de 0,25° (cerca de 28 × 28 km) cujo centro está dentro da área. "
          "É a resolução usada para harmonizar MODIS e VIIRS; áreas menores que uma célula usam a célula do centro.",
    h_val_modis="Erro médio (MAPE) ao usar o MODIS sem ajuste no lugar do VIIRS, comparado com o VIIRS real em "
                "2022–2025. Mostra por que a harmonização é necessária.",
    h_val_kglob="Erro médio (MAPE) usando um único fator k para todo o Brasil (VIIRS ÷ MODIS calibrado em "
                "abr/2018–2021) e testado em 2022–2025.",
    h_val_khier="Erro médio (MAPE) usando um fator k por célula de 0,25°, puxado para o valor da região de 2° e do "
                "Brasil quando há poucos dados (shrinkage). É o método usado no app. Quanto menor, melhor.",
    h_rt_total="Focos detectados pelos satélites VIIRS (NOAA-20, NOAA-21 e S-NPP) nas últimas 24 h dentro da área "
               "de interesse. Contagem bruta, sem harmonização.",
    h_rt_recente="Data e hora (Brasília) da passagem de satélite mais recente que detectou foco na área. "
                 "O dado chega ao FIRMS cerca de 3 h depois da passagem.",
    h_rt_frp="Fire Radiative Power: energia irradiada pelo fogo no momento da detecção, em megawatts. Indica a "
             "intensidade: até ~10 MW é fogo pequeno; dezenas, fogo forte; centenas, incêndio grande. "
             "Mostra o maior valor entre os focos da área.",
    h_rt_area="Total de focos nas últimas 24 h em todo o Brasil, para comparar com a área de interesse.",
    al_limpar_ok="Apagar histórico", al_chip="🔔 Alertas ativos ({n})",
    ax_mes="Mês", ax_ano="Ano", ax_focos="Focos", ax_pct="% vs mediana", ax_serie="Série",
    s_modis="MODIS bruto", s_viirs="VIIRS NOAA-20 bruto", s_harm="Harmonizado",
    s_real="VIIRS real", s_prev="Previsto (k hierárquico)",
    m_kglob="k único", m_khier="k hierárquico",
    mes_comp="Mês para comparar", mediana="Mediana",
    ref_lbl="Referência", ref_med="Mediana", ref_mean="Média plurianual", media="Média",
    ax_pct_mean="% vs média",
    titulo_comp="Focos em {j} de cada ano",
    rank="{a} está em {p}º lugar entre {n} anos ({j}).",
    cap_comp="Barras: focos VIIRS-equivalentes no mesmo período de cada ano, de 2003 até hoje (não depende do filtro de período). Em destaque: {a}. Linha tracejada vermelho-alaranjada: mediana dos anos anteriores; linha pontilhada verde: média.",  # [linhas]
    cap_cal="Paleta YlOrRd (ColorBrewer, acessível para daltônicos e legível em tons de cinza): cor mais escura = mais focos. Passe o mouse para ver o valor exato.",
    cap_anom="Escala RdBu (acessível para daltônicos): vermelho = acima da mediana do mesmo mês, azul = abaixo, branco = normal.",
    cap_anom_mean="Escala RdBu (acessível para daltônicos): vermelho = acima da média do mesmo mês, azul = abaixo, branco = normal. A média é mais sensível a anos extremos (ex.: 2007, 2010, 2024) que a mediana.",
    cap_serie="Linha cinza tracejada: início do NOAA-20 (abr/2018). Antes dela, Harmonizado = k × MODIS. Cores Okabe-Ito + tipos de linha distintos.",
    cap_val="Calibrado em abr/2018–2021, testado em 2022–2025 (Brasil, mensal). Métrica: MAPE. Cores Okabe-Ito + tipos de linha distintos.",
    dl_cal="Calendário (CSV)", dl_serie="Série mensal (CSV)", dl_prep="Preparar CSV dos focos da área",
    dl_focos="Focos", linhas="linhas",
    dl_hint="Os gráficos também podem ser baixados em PNG pelo ícone de câmera no canto de cada gráfico.",
),
"EN": dict(
    meses=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    config="Settings", idioma="Language", tema="Theme", light="Light", dark="Dark",
    filtros="Filters", area="Area of interest",
    draw="Draw on map", coords="Coordinates", estado="States",                 # [estado]
    upload="Upload file", pais="Whole country",                                # [upload] [país]
    uf_lbl="States", uf_ph="Choose one or more states",                        # [estado]
    uf_err="Could not load state boundaries (IBGE). Save a GeoJSON of the states to "
           "data/raw/estados.geojson and reload the page.",
    pais_hint="Colors hotspot intensity across all of Brazil and, in the Real time tab, shows every hotspot "
              "in the country. May take a few seconds the first time.",
    brasil="Brazil",
    # [várias áreas]
    area_lbl="Area: {a}", area_n_lbl="{n} areas selected",
    areas_titulo="Your areas (click a name to edit it)", rm_area="Remove this area", limpar_areas="Remove all areas",
    nome_draw="Drawing", nome_coords="Polygon", nome_upload="File", concluir="Finish area",
    fontes_hint="Check one or more ways to choose areas; they can be combined (e.g., a file and a drawing).",
    nome_area="Area name (optional)", nome_lbl="Area name", fonte_off="Source unchecked: areas kept, but left out of the analysis.",
    lat_min="Min lat", lat_max="Max lat", lon_min="Min lon", lon_max="Max lon",
    limpar="Clear selection",
    rm_btn="Remove selected area",                                             # [remover área]
    rm_tip="Click the area to remove it (Esc cancels)",                        # [remover área]
    rm_vazio="No area to remove",                                              # [remover área]
    draw_hint="Draw polygons or rectangles using the tools in the top-left corner of the map. "
              "Each drawing becomes an area; you can add several.",
    # [upload] area boundary from a file
    up_lbl="Area boundary file",
    up_hint="KML, KMZ, GeoJSON or zipped shapefile (.zip with .shp, .shx and .dbf), in lat/lon degrees "
            "(WGS84 or SIRGAS 2000). E.g., the property perimeter downloaded from CAR/SICAR. "
            "You can upload several files: each becomes an area (polygons in the same file are merged).",
    up_ler="Could not read the file. Check that it is a valid KML, KMZ, GeoJSON or zipped shapefile.",
    up_vazio="The file contains no polygons (only points or lines). Upload the area outline.",
    up_graus="The file coordinates are not in latitude/longitude degrees (they may be UTM). "
             "Export it in geographic WGS84 or SIRGAS 2000.",
    up_pyshp="To read shapefiles, install the pyshp package (pip install pyshp) or upload KML/GeoJSON.",
    up_tipo="Unsupported format. Use KML, KMZ, GeoJSON or a zipped shapefile.",
    err_lat="Invalid coordinates: minimum latitude must be lower than maximum latitude.",
    err_lon="Invalid coordinates: minimum longitude must be lower than maximum longitude.",
    err_fora="The area is outside data coverage (Brazil). Showing all of Brazil.",
    lat="Latitude", lon="Longitude", add_pt="Add point",
    pts_titulo="Added points", rm_pt="Remove this point", limpar_pts="Clear points",
    pt_fora="Point outside the map area (South America: lat −60 to 15, lon −95 to −25).",
    pt_dup="This point has already been added.",
    pt_min="Add at least 3 points ({n}/3) and click “Finish area”. Points are connected in the order they were added. Repeat to add more areas.",
    poly_linha="The points are aligned and do not form an area. Add a point off that line.",
    poly_cruza="The area's edges cross each other. Remove points or add them in sequence around the area.",
    periodo="Period", de="From", ate="To", mes="Month", ano="Year",
    per_hint="“To” options start at the month chosen in “From”.",
    disp="Available data: {a} – {b}.",
    err_periodo="Start was after end; dates were swapped.",
    ajuste="Period adjusted to the range with data.",
    aviso_2000="In 2000–2002 only the Terra satellite was operating; counts are underestimated.",
    info="Information", acess="Accessibility", sobre="About the data",
    acess_txt="""
All colors were chosen to be distinguishable by people with color vision deficiency:
- **Map and calendar:** *YlOrRd* palette (ColorBrewer), colorblind-safe and readable in grayscale; from light yellow (fewer hotspots) to dark red (more hotspots). On the map, color is shown only inside the selected area, with a legend below.
- **Anomaly:** diverging *RdBu* scale (ColorBrewer): blue = below the median, white = normal, red = above.
- **Year comparison:** highlighted year in blue (*Okabe-Ito*), other years in gray; median as a dashed vermilion line and mean as a dotted green line, with values labeled beside the chart.
- **Line charts:** *Okabe-Ito* palette, and each series also has a distinct line style.
- Indicators show a sign (+/−) and an arrow, not just color.
- Light and dark themes available in ⚙ Settings.
""",
    sobre_txt="""
- **Source:** NASA FIRMS — MODIS C6.1 (2000–2025) and VIIRS NOAA-20 375 m (2018–present).
- **Coverage:** Brazil. Gray areas on the map are outside coverage.
- **Unit:** VIIRS-equivalent hotspots.
- **Harmonization:** per-cell *k* factor (0.25°), calibrated on the Apr 2018–Dec 2025 overlap, with *shrinkage* toward 2° regions and toward Brazil.
- Before Apr 2018: *k* × MODIS. After: VIIRS NOAA-20.
""",
    resize_hint="↔ Drag the right edge of this panel to resize it.",
    eyebrow="NASA Space Apps 2026 · NASA FIRMS data", titulo="Flama",
    sub="Burning Activity Calendar · Harmonized MODIS + VIIRS active fire hotspot series · Brazil",
    dados_ate="Data through", area_coords="Area: coordinates", area_poly="Area: drawn polygon",
    area_up="Area: uploaded file",                                             # [upload]
    area_br="Area: all of Brazil",
    l_sat="Satellite", l_fora="Outside coverage", l_limite="Brazil boundary",
    l_focos="Fire hotspots", l_sel="Selected area", l_rot="Labels",
    gerando="Rendering area map...", calculando="Computing current-month comparison...",
    leg_titulo="Hotspot intensity per year", menor="Lower", maior="Higher",
    leg_nota="Log scale, relative to the displayed area · accessible palette",
    fora_cob="Outside data coverage",
    sel_hint="Select an area of interest (or “Whole country”) to display hotspot intensity on the map. Indicators and charts: all of Brazil.",
    sem_focos="No hotspots recorded in this area.",
    kpi_total="Total hotspots in period", kpi_vs="vs median", focos="hotspots",
    kpi_ano="Year with most hotspots", kpi_mes="Most critical month (median)", kpi_cel="Selected 0.25° cells",
    kpi_temp="Typical fire season (peak)",                                     # [temporada]
    temp_help="Start: month by which 10% of the year's hotspots have usually accumulated. End: month reaching "
              "90%. In parentheses: the peak month.",
    unidade="Unit: VIIRS-equivalent hotspots (NOAA-20, 375 m).",
    nota_parcial="The current month is not over yet: the indicator compares days 1–{d} of {m} this year with the median of the same window in {a0}–{a1}.",
    abas=["Calendar", "Anomaly", "Year comparison", "Time series", "Validation", "Downloads",
          "Real time", "Alerts"],                                              # [tempo real] [alertas]
    # [tempo real]
    rt_sem_chave="For real-time monitoring, set the FIRMS API key (MAP_KEY) in `.streamlit/secrets.toml` "
                 "(`FIRMS_KEY = \"...\"`) or in the `FIRMS_KEY` environment variable. "
                 "The key is free: firms.modaps.eosdis.nasa.gov/api/map_key",
    rt_buscando="Querying FIRMS...",
    rt_status="Updated at {h} (Brasília time) · next update around {p} · every {n} min",
    rt_agora="Update now",
    rt_total="Hotspots in the last 24 h", rt_area="All of Brazil (24 h)",
    rt_sem_area="Select an area of interest under Filters (or “Whole country”) to see its real-time hotspots.",
    rt_recente="Most recent detection", rt_frp="Max FRP (MW)",
    rt_erro="No response from FIRMS for: {s}. Data shown may be incomplete.",
    rt_vazio="No hotspots in the last 24 h.", rt_horas="Hours ago",
    rt_hover="Detected: {h} (Brasília)<br>Satellite: {s}<br>FRP: {f} MW",
    rt_cap="Source: NASA FIRMS, VIIRS NRT (NOAA-20, NOAA-21 and S-NPP), nominal or high confidence, last 24 h, "
           "within the area of interest. Each satellite pass reaches FIRMS about 3 h later. Darker color = more recent "
           "detection. Real-time hotspots are not harmonized (raw counts).",
    rt_dl="Hotspots from the last 24 h in the area (CSV)",
    rt_intervalo="Real-time refresh",
    rt_int_help="How often the app queries FIRMS. FIRMS receives new data with each satellite pass, so "
                "intervals shorter than 10 min rarely bring new hotspots.",
    # [alertas]
    al_titulo="Fire alerts", al_on="Receive alerts",
    al_hint="Alerts monitor the areas of interest chosen under Filters (each area separately).",
    al_toast="{n} new hotspot(s) in {a}",
    al_off="Alerts are off. Turn them on in ⚙ Settings → Fire alerts.",
    al_status="Monitoring: {a} · checked every {n} min. An alert is raised when a new hotspot "
              "(VIIRS NRT) appears inside the area.",
    al_sem_area="No area of interest selected. Choose one or more under Filters → Area of interest.",
    al_sem_chave="Alerts require the FIRMS API key (see the Real time tab).",
    al_vazio="No alerts recorded yet.",
    al_ultimos="Latest alerts",
    al_cols=dict(quando="Checked at (Brasília)", area="Area", focos="New hotspots",
                 frp="Max FRP (MW)", ultima="Latest detection (UTC)"),
    al_dl="Alert hotspots (CSV)", al_dl_res="Alert summary (CSV)",
    al_limpar="Clear history", al_limpar_conf="Deletes all saved alerts. This cannot be undone.",
    # [info] indicator explanations (ⓘ icon)
    h_total="Sum of hotspots in the area and period chosen under Filters, already harmonized (VIIRS-equivalent): "
            "before Apr 2018 they come from MODIS multiplied by the k factor; after that, from VIIRS NOAA-20.",
    h_vs="Hotspots in the current month, from day 1 to the last day with data, compared with the median of the "
         "same days in previous years (since 2003). Red with an up arrow = above normal; green with a down arrow = below.",
    h_ano="Year with the highest total of hotspots in the area, within the chosen period.",
    h_cel="Number of 0.25° grid cells (about 28 × 28 km) whose center lies inside the area. This is the resolution "
          "used to harmonize MODIS and VIIRS; areas smaller than one cell use the cell at their center.",
    h_val_modis="Mean error (MAPE) when using unadjusted MODIS in place of VIIRS, compared with observed VIIRS in "
                "2022–2025. Shows why harmonization is needed.",
    h_val_kglob="Mean error (MAPE) using a single k factor for all of Brazil (VIIRS ÷ MODIS calibrated on "
                "Apr 2018–2021) and tested on 2022–2025.",
    h_val_khier="Mean error (MAPE) using a k factor per 0.25° cell, pulled toward the 2° region and Brazil values "
                "when data is scarce (shrinkage). This is the method used in the app. Lower is better.",
    h_rt_total="Hotspots detected by the VIIRS satellites (NOAA-20, NOAA-21 and S-NPP) in the last 24 h inside the "
               "area of interest. Raw count, not harmonized.",
    h_rt_recente="Date and time (Brasília) of the most recent satellite pass that detected a hotspot in the area. "
                 "Data reaches FIRMS about 3 h after the pass.",
    h_rt_frp="Fire Radiative Power: energy radiated by the fire at detection time, in megawatts. It indicates "
             "intensity: up to ~10 MW is a small fire; tens, a strong fire; hundreds, a large wildfire. "
             "Shows the highest value among the area's hotspots.",
    h_rt_area="Total hotspots in the last 24 h across Brazil, for comparison with the area of interest.",
    al_limpar_ok="Delete history", al_chip="🔔 Alerts on ({n})",
    ax_mes="Month", ax_ano="Year", ax_focos="Hotspots", ax_pct="% vs median", ax_serie="Series",
    s_modis="Raw MODIS", s_viirs="Raw VIIRS NOAA-20", s_harm="Harmonized",
    s_real="Observed VIIRS", s_prev="Predicted (hierarchical k)",
    m_kglob="Single k", m_khier="Hierarchical k",
    mes_comp="Month to compare", mediana="Median",
    ref_lbl="Baseline", ref_med="Median", ref_mean="Multi-year mean", media="Mean",
    ax_pct_mean="% vs mean",
    titulo_comp="Hotspots in {j} of each year",
    rank="{a} ranks #{p} out of {n} years ({j}).",
    cap_comp="Bars: VIIRS-equivalent hotspots in the same window of each year, from 2003 to today (independent of the period filter). Highlighted: {a}. Dashed vermilion line: median of previous years; dotted green line: mean.",  # [linhas]
    cap_cal="YlOrRd palette (ColorBrewer, colorblind-safe and readable in grayscale): darker color = more hotspots. Hover to see exact values.",
    cap_anom="RdBu scale (colorblind-safe): red = above the median for the same month, blue = below, white = normal.",
    cap_anom_mean="RdBu scale (colorblind-safe): red = above the mean for the same month, blue = below, white = normal. The mean is more sensitive to extreme years (e.g., 2007, 2010, 2024) than the median.",
    cap_serie="Dashed gray line: start of NOAA-20 (Apr 2018). Before it, Harmonized = k × MODIS. Okabe-Ito colors + distinct line styles.",
    cap_val="Calibrated on Apr 2018–2021, tested on 2022–2025 (Brazil, monthly). Metric: MAPE. Okabe-Ito colors + distinct line styles.",
    dl_cal="Calendar (CSV)", dl_serie="Monthly series (CSV)", dl_prep="Prepare hotspot CSV for area",
    dl_focos="Hotspots", linhas="rows",
    dl_hint="Charts can also be downloaded as PNG via the camera icon on each chart.",
),
}

# textos das ferramentas de desenho do mapa (Leaflet.draw) e do zoom
DRAW_TXT = {
    "PT": dict(
        actions={"title": "Cancelar o desenho", "text": "Cancelar"},
        finish={"title": "Concluir o desenho", "text": "Concluir"},
        undo={"title": "Apagar o último ponto desenhado", "text": "Apagar último ponto"},
        polygon="Desenhar um polígono", rectangle="Desenhar um retângulo",
        poly_tip={"start": "Clique para começar a desenhar a área.",
                  "cont": "Clique para continuar desenhando.",
                  "end": "Clique no primeiro ponto para fechar a área."},
        cross="<strong>Erro:</strong> as bordas da área não podem se cruzar.",
        rect_start="Clique e arraste para desenhar um retângulo.",
        release="Solte o botão do mouse para concluir.",
        zoom_in="Aproximar", zoom_out="Afastar",
        lbl_poly="Desenhar polígono", lbl_rect="Desenhar retângulo",
    ),
    "EN": dict(
        actions={"title": "Cancel drawing", "text": "Cancel"},
        finish={"title": "Finish drawing", "text": "Finish"},
        undo={"title": "Delete last point drawn", "text": "Delete last point"},
        polygon="Draw a polygon", rectangle="Draw a rectangle",
        poly_tip={"start": "Click to start drawing the area.",
                  "cont": "Click to continue drawing.",
                  "end": "Click the first point to close the area."},
        cross="<strong>Error:</strong> area edges cannot cross.",
        rect_start="Click and drag to draw a rectangle.",
        release="Release the mouse button to finish.",
        zoom_in="Zoom in", zoom_out="Zoom out",
        lbl_poly="Draw polygon", lbl_rect="Draw rectangle",
    ),
}

def draw_i18n_js(lang):
    s = json.dumps(DRAW_TXT[lang], ensure_ascii=False)
    return f"""
    (function () {{
      var s = {s};
      if (window.L && L.drawLocal) {{
        var d = L.drawLocal.draw;
        d.toolbar.actions = s.actions; d.toolbar.finish = s.finish; d.toolbar.undo = s.undo;
        d.toolbar.buttons.polygon = s.polygon; d.toolbar.buttons.rectangle = s.rectangle;
        d.handlers.polygon.tooltip = s.poly_tip;
        d.handlers.polyline.error = s.cross;
        d.handlers.rectangle.tooltip = {{start: s.rect_start}};
        d.handlers.simpleshape.tooltip = {{end: s.release}};
      }}
      function zoomTitles() {{
        var zi = document.querySelector('.leaflet-control-zoom-in'),
            zo = document.querySelector('.leaflet-control-zoom-out');
        if (zi) zi.title = s.zoom_in;
        if (zo) zo.title = s.zoom_out;
      }}
      setTimeout(zoomTitles, 300); setTimeout(zoomTitles, 1500);
    }})();
    """

# [remover área] botão ✕ na barra da esquerda: ativa o modo remover; clicar numa área a remove.
# Ao remover, envia ao app um "clique" numa latitude impossível (−89,9 − índice × 0,001), que serve de sinal
# e diz qual área foi clicada.
RM_LAT = -89.9
RM_PASSO = 0.001

def rm_ctl_js(mapa, camadas, s):
    s = json.dumps(s, ensure_ascii=False)
    return f"""
    (function () {{
      var map = {mapa}, areas = [{", ".join(camadas)}], s = {s}, ativo = false, btn;
      var base = {{color: s.base, weight: 1.5, fillOpacity: 0}},
          marc = {{color: s.cor, weight: 2.5, fillColor: s.cor, fillOpacity: 0.06}};
      function modo(on) {{
        ativo = on;
        btn.classList.toggle('ativo', on);
        map.getContainer().classList.toggle('modo-rm', on);
        areas.forEach(function (a) {{
          a.setStyle(on ? marc : base);
          if (on) a.bindTooltip(s.tip, {{sticky: true}}); else a.unbindTooltip();
        }});
      }}
      var Ctl = L.Control.extend({{
        options: {{position: 'topleft'}},
        onAdd: function () {{
          var box = L.DomUtil.create('div', 'leaflet-bar rm-ctl' + (areas.length ? '' : ' vazio'));
          btn = L.DomUtil.create('a', 'rm-btn', box);
          btn.href = '#'; btn.innerHTML = '&#x2715;';
          btn.title = areas.length ? s.btn : s.vazio;
          btn.setAttribute('role', 'button'); btn.setAttribute('aria-label', btn.title);
          L.DomEvent.disableClickPropagation(box);
          L.DomEvent.on(btn, 'click', function (e) {{
            L.DomEvent.preventDefault(e);
            if (areas.length) modo(!ativo);
          }});
          return box;
        }}
      }});
      new Ctl().addTo(map);
      areas.forEach(function (area, i) {{
        area.on('mouseover', function () {{ if (ativo) area.setStyle({{fillOpacity: 0.18}}); }});
        area.on('mouseout', function () {{ if (ativo) area.setStyle({{fillOpacity: 0.06}}); }});
        area.on('click', function (e) {{
          if (!ativo) return;
          L.DomEvent.stopPropagation(e);
          modo(false);
          area.setStyle({{opacity: 0, fillOpacity: 0}});
          setTimeout(function () {{
            var sinal = L.latLng({RM_LAT} - i * {RM_PASSO}, (Date.now() % 100000) / 1000);
            area.eachLayer(function (l) {{ l.fire('click', {{latlng: sinal}}, true); }});
          }}, 60);
        }});
      }});
      document.addEventListener('keydown', function (e) {{ if (e.key === 'Escape' && ativo) modo(false); }});
    }})();
    """

class JsSnippet(MacroElement):
    """Insere um trecho de JavaScript no script do mapa, na ordem em que é adicionado."""
    def __init__(self, js):
        super().__init__()
        self._template = Template("{% macro script(this, kwargs) %}" + js + "{% endmacro %}")

st.set_page_config(page_title="Flama", page_icon="🔥",
                   layout="wide", initial_sidebar_state="expanded")

# ---------------- dados
@st.cache_data
def load():
    h = pd.read_parquet("data/proc/harmonized.parquet",
                        columns=["gx", "gy", "month", "modis", "viirs", "H", "k"])
    kt = h.groupby(["gx", "gy"], as_index=False).k.first()
    cells = kt[["gx", "gy"]].copy()
    cells["lon"] = (cells.gx + 0.5) * RES
    cells["lat"] = (cells.gy + 0.5) * RES
    val = pd.read_parquet("data/proc/validation.parquet")
    return h, cells, kt, val

@st.cache_data
def mascara():
    if not os.path.exists(BR_FILE):
        return None, None
    br = shape(json.load(open(BR_FILE))["features"][0]["geometry"]).simplify(0.02)
    fora = box(-180, -85, 180, 85).difference(br)          # tudo menos o Brasil
    return mapping(fora), mapping(br)

@st.cache_data(show_spinner=False)
def estados():
    """[estado] {sigla: wkt}. Lê data/raw/estados.geojson; se não existir, baixa a malha das UFs do IBGE e salva."""
    try:
        if os.path.exists(UF_FILE):
            with open(UF_FILE, encoding="utf-8") as f:
                gj = json.load(f)
        else:
            import requests
            r = requests.get(UF_URL, params=UF_PARAMS, timeout=60)
            r.raise_for_status()
            gj = r.json()
            os.makedirs(os.path.dirname(UF_FILE), exist_ok=True)
            with open(UF_FILE, "w", encoding="utf-8") as f:
                json.dump(gj, f)
    except Exception:
        return {}
    sigla_ok = set(UF_NOME)
    out = {}
    for ft in gj.get("features", []):
        p = {k.lower(): v for k, v in (ft.get("properties") or {}).items()}
        sigla = None
        cod = next((p[k] for k in ("codarea", "cd_uf", "cod_uf", "codigo_uf", "code") if p.get(k)), None)
        if cod is not None and str(cod)[:2].isdigit():
            sigla = UF.get(int(str(cod)[:2]), (None,))[0]
        if sigla is None:
            sigla = next((str(p[k]).upper() for k in ("sigla", "sigla_uf", "uf", "abbrev") if p.get(k)), None)
        if sigla in sigla_ok and ft.get("geometry"):
            g = shapely.make_valid(shape(ft["geometry"])).simplify(0.005)
            out[sigla] = g.wkt
    return out

def firms_key():
    """[tempo real] Chave da API do FIRMS: st.secrets["FIRMS_KEY"] ou variável de ambiente FIRMS_KEY."""
    k = os.environ.get("FIRMS_KEY")
    try:
        k = st.secrets.get("FIRMS_KEY", k)
    except Exception:                                       # sem secrets.toml
        pass
    return k

@st.cache_data(show_spinner=False, max_entries=4)
def focos_nrt(key, marca):
    """[tempo real] Focos VIIRS NRT das últimas 24 h no Brasil. `marca` muda a cada atualização e força nova consulta."""
    import requests
    dfs, erros = [], []
    for src, sat in NRT_SRC.items():
        try:
            r = requests.get(FIRMS_URL.format(key=key, src=src, bbox=BBOX_BR, dias=2), timeout=60)
            if r.status_code != 200 or not r.text.startswith("latitude"):
                erros.append(sat)
                continue
            df = pd.read_csv(io.StringIO(r.text))
            df["satelite"] = sat
            dfs.append(df)
        except Exception:
            erros.append(sat)
    agora = pd.Timestamp.now(tz="UTC")
    if not dfs:
        return pd.DataFrame(columns=HIST_COLS[4:]), erros, agora
    df = pd.concat(dfs, ignore_index=True)
    for c in ("latitude", "longitude", "frp", "acq_time"):                      # garante tipo numérico
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude", "acq_time"])
    df = df[df.confidence.astype(str).str[0].isin(["n", "h"])]
    df["data_hora_utc"] = pd.to_datetime(df.acq_date.astype(str) + " "
                                         + df.acq_time.astype(int).astype(str).str.zfill(4),
                                         format="%Y-%m-%d %H%M", utc=True)
    df = df[df.data_hora_utc >= agora - pd.Timedelta(hours=24)]
    if BR_SHAPE is not None and len(df):
        df = df[shapely.contains_xy(BR_SHAPE, df.longitude.values, df.latitude.values)]
    df = df.rename(columns={"confidence": "confianca"})
    df["id"] = (df.latitude.round(4).astype(str) + "_" + df.longitude.round(4).astype(str) + "_"
                + df.data_hora_utc.dt.strftime("%Y%m%d%H%M") + "_" + df.satelite)
    return df[HIST_COLS[4:]].drop_duplicates("id").reset_index(drop=True), erros, agora

@st.cache_resource(show_spinner=False)
def poly_prep(wkt):
    p = shapely.from_wkt(wkt)
    shapely.prepare(p)
    return p

def carregar_hist():
    """[alertas] Histórico salvo em disco (sobrevive a recarregar a página)."""
    if os.path.exists(ALERT_FILE):
        try:
            return pd.read_csv(ALERT_FILE, dtype={"alerta_id": str, "id": str, "area": str,
                                                  "area_key": str}).reindex(columns=HIST_COLS)
        except Exception:
            pass
    return pd.DataFrame(columns=HIST_COLS)

def salvar_hist(novos):
    os.makedirs(os.path.dirname(ALERT_FILE), exist_ok=True)
    novos.to_csv(ALERT_FILE, mode="a", header=not os.path.exists(ALERT_FILE), index=False)

def chave_area(wkt):
    """[alertas] Identificador estável de uma área (pela geometria), para não repetir alertas."""
    return hashlib.md5(wkt.encode()).hexdigest()[:12]

def checar_alertas(df, areas):
    """[alertas] Registra focos ainda não vistos dentro de cada área. Retorna True se houve alerta novo."""
    if df.empty or not areas:
        return False
    agora = pd.Timestamp.now(tz=TZ_BR)
    novos = []
    for nome, wkt in areas:
        chave = chave_area(wkt)
        p = poly_prep(wkt)
        d = df[shapely.contains_xy(p, df.longitude.values, df.latitude.values)]
        d = d[[(chave, i) not in ss.vistos for i in d.id]]
        if d.empty:
            continue
        ss.vistos.update((chave, i) for i in d.id)
        d = d.assign(alerta_id=f"{agora:%Y%m%d%H%M%S}-{len(novos)}",
                     verificado_em=agora.strftime("%Y-%m-%d %H:%M"), area=nome, area_key=chave,
                     data_hora_utc=d.data_hora_utc.dt.strftime("%Y-%m-%d %H:%M"))
        novos.append(d[HIST_COLS])
    if not novos:
        return False
    nv = pd.concat(novos, ignore_index=True)
    salvar_hist(nv)
    ss.hist = nv if ss.hist.empty else pd.concat([ss.hist, nv], ignore_index=True)
    for a, n in nv.groupby("area").size().items():
        ss.toasts.append(T["al_toast"].format(n=n, a=a))
    return True

def contorno(geom):
    """Coordenadas (lon, lat) das bordas de um polígono/multipolígono, separadas por None, para traçar linhas."""
    xs, ys = [], []
    for g in shapely.get_parts(geom):
        for anel in [g.exterior, *g.interiors] if hasattr(g, "exterior") else []:
            x, y = anel.xy
            xs += list(x) + [None]
            ys += list(y) + [None]
    return xs, ys

def painel_tempo_real(key, intervalo, areas, foco_wkt, pais):
    """[tempo real] Conteúdo da aba; roda como fragmento que se atualiza sozinho a cada `intervalo` minutos.
    `foco_wkt`: união das áreas de interesse (None = nenhuma); `pais`: modo País inteiro."""
    c1, c2 = st.columns([4, 1])
    forcar = c2.button(T["rt_agora"], use_container_width=True, key="rt_btn")
    if forcar or time.time() - ss.get("nrt_t", 0) >= intervalo * 60 - 30:
        ss.nrt_t = time.time()
    with st.spinner(T["rt_buscando"]):
        df, erros, quando = focos_nrt(key, ss.nrt_t)
    if checar_alertas(df, areas):
        st.rerun(scope="app")                               # atualiza a aba Alertas e mostra os avisos

    hora = quando.tz_convert(TZ_BR)
    prox = pd.Timestamp(ss.nrt_t + intervalo * 60, unit="s", tz="UTC").tz_convert(TZ_BR)
    c1.caption(T["rt_status"].format(h=hora.strftime("%H:%M"), p=prox.strftime("%H:%M"), n=intervalo))
    if erros:
        st.warning(T["rt_erro"].format(s=", ".join(erros)), icon=":material/warning:")
    if foco_wkt is None:
        st.info(T["rt_sem_area"], icon=":material/info:")
        return

    # só os focos dentro da área de interesse (no modo País inteiro, todos)
    foco = poly_prep(foco_wkt)
    d = df if pais or df.empty else df[shapely.contains_xy(foco, df.longitude.values, df.latitude.values)]

    k = st.columns(3 if pais else 4)
    k[0].metric(T["rt_total"], f"{len(d):,}", help=T["h_rt_total"])
    k[1].metric(T["rt_recente"], d.data_hora_utc.max().tz_convert(TZ_BR).strftime("%d/%m %H:%M") if len(d) else "—",
                 help=T["h_rt_recente"])
    k[2].metric(T["rt_frp"], f"{d.frp.max():,.1f}" if len(d) else "—", help=T["h_rt_frp"])
    if not pais:
        k[3].metric(T["rt_area"], f"{len(df):,}", help=T["h_rt_area"])

    # mapa: contorno das áreas + focos coloridos pela idade
    Sc = getattr(go, "Scattermap", None)                    # plotly >= 5.24 (MapLibre)
    chave_mapa = "map" if Sc is not None else "mapbox"
    Sc = Sc or go.Scattermapbox
    fig = go.Figure()
    if not pais:
        xs, ys = contorno(foco)
        fig.add_trace(Sc(lon=xs, lat=ys, mode="lines", line=dict(width=2, color=P["text"]),
                         hoverinfo="skip", showlegend=False))
    if len(d):
        d = d.assign(h=((quando - d.data_hora_utc).dt.total_seconds() / 3600).round(1),
                     hora_br=d.data_hora_utc.dt.tz_convert(TZ_BR).dt.strftime("%d/%m %H:%M"))
        d = d.sort_values("h", ascending=False)             # mais recentes por cima
        escala = [[i / (len(PAL) - 1), c] for i, c in enumerate(PAL[::-1])]
        fig.add_trace(Sc(lon=d.longitude, lat=d.latitude, mode="markers", showlegend=False,
                         marker=dict(size=7, opacity=0.85, color=d.h, colorscale=escala, cmin=0, cmax=24,
                                     colorbar=dict(title=dict(text=T["rt_horas"], font=dict(color=P["text2"])),
                                                   thickness=10, outlinewidth=0, len=0.8,
                                                   tickfont=dict(color=P["text2"]))),
                         customdata=d[["hora_br", "satelite", "frp"]].values,
                         hovertemplate=T["rt_hover"].format(h="%{customdata[0]}", s="%{customdata[1]}",
                                                            f="%{customdata[2]:.1f}") + "<extra></extra>"))
    if pais:
        centro, zoom = dict(lat=-14.5, lon=-52), 3.2
    else:
        x0, y0, x1, y1 = foco.bounds
        centro = dict(lat=(y0 + y1) / 2, lon=(x0 + x1) / 2)
        zoom = float(np.clip(np.log2(360 / max(x1 - x0, y1 - y0, 0.05)) - 1.3, 3, 13))
    fig.update_layout(**{chave_mapa: dict(style="carto-darkmatter" if ESCURO else "carto-positron",
                                          center=centro, zoom=zoom)},
                      height=540, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      uirevision=foco_wkt[:200] if not pais else "pais",
                      font=dict(family="Inter, system-ui, sans-serif", color=P["text2"]),
                      hoverlabel=dict(bgcolor=P["surface"], bordercolor=P["border"], font=dict(color=P["text"])))
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CFG, theme=None, key="rt_mapa")
    if d.empty:
        st.caption(T["rt_vazio"])
    st.caption(T["rt_cap"])
    if len(d):
        out = d[HIST_COLS[4:]].assign(data_hora_utc=d.data_hora_utc.dt.strftime("%Y-%m-%d %H:%M"))
        st.download_button(T["rt_dl"], out.to_csv(index=False).encode(), "focos_24h.csv", key="rt_dl")

@st.cache_data
def ultima_data():
    return pd.Timestamp(duckdb.execute(f"SELECT max(date) FROM '{PTS}'").fetchone()[0])

h, cells, kt, val = load()
K_DOM = float(kt.k.median())
ULT = ultima_data()                                         # último dia com dados
ULT_MES = h.month.max()                                     # último mês na série mensal
fora_br, contorno_br = mascara()
BR_SHAPE = shape(contorno_br) if contorno_br is not None else None

merc = lambda lat: np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
inv_merc = lambda y: np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)

def suavizar(a, s=1.0):
    r = int(3 * s)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    a = np.apply_along_axis(np.convolve, 0, a, k, mode="same")
    return np.apply_along_axis(np.convolve, 1, a, k, mode="same")

@st.cache_data(show_spinner=False)
def raster(wkt, d0, d1, n_meses):
    """Intensidade da área (log1p dos focos harmonizados/ano), sem normalizar: a normalização é feita em
    conjunto para todas as áreas selecionadas, e a cor é aplicada fora do cache."""
    poly = shapely.from_wkt(wkt)
    shapely.prepare(poly)                                   # acelera o contains_xy (ex.: Brasil inteiro)
    x0, y0, x1, y1 = poly.bounds
    res = max(max(x1 - x0, y1 - y0) / 500, 0.004)          # ~400 m no mínimo (resolução do VIIRS)
    dm = np.radians(res)                                    # passo vertical em Mercator
    gx0 = np.floor(x0 / res) * res
    gm0 = np.floor(merc(y0) / dm) * dm
    nx = int(np.ceil((x1 - gx0) / res))
    ny = int(np.ceil((merc(y1) - gm0) / dm))

    con = duckdb.connect()
    con.register("kt", kt)
    df = con.execute(f"""
        WITH p AS (
            SELECT longitude, latitude, sensor,
                   CAST(floor(longitude / {RES}) AS INT) AS gx,
                   CAST(floor(latitude / {RES}) AS INT) AS gy
            FROM '{PTS}'
            WHERE longitude BETWEEN {x0} AND {x1} AND latitude BETWEEN {y0} AND {y1}
              AND date >= '{d0}' AND date < '{d1}'
              AND ((sensor = 'viirs' AND date >= '{OV_START}')
                OR (sensor = 'modis' AND date <  '{OV_START}')))
        SELECT CAST(floor((longitude - {gx0}) / {res}) AS INT) AS ix,
               CAST(floor((ln(tan(pi() / 4 + radians(latitude) / 2)) - {gm0}) / {dm}) AS INT) AS iy,
               SUM(CASE WHEN sensor = 'viirs' THEN 1 ELSE COALESCE(kt.k, {K_DOM}) END) AS w
        FROM p LEFT JOIN kt USING (gx, gy)
        GROUP BY 1, 2""").df()

    img = np.zeros((ny, nx))
    df = df[(df.ix >= 0) & (df.ix < nx) & (df.iy >= 0) & (df.iy < ny)]
    np.add.at(img, (df.iy.values, df.ix.values), df.w.values / (n_meses / 12))
    img = suavizar(img)

    xs = gx0 + (np.arange(nx) + 0.5) * res
    ys = inv_merc(gm0 + (np.arange(ny) + 0.5) * dm)
    XX, YY = np.meshgrid(xs, ys)
    dentro = shapely.contains_xy(poly, XX, YY)

    v = np.log1p(img)
    if not (dentro & (v > 0)).any():
        return None
    bounds = [[float(inv_merc(gm0)), float(gx0)],
              [float(inv_merc(gm0 + ny * dm)), float(gx0 + nx * res)]]
    return v, dentro, bounds

@st.cache_data(show_spinner=False)
def janela_por_ano(sel_cells, mes, dia_fim):
    """Focos harmonizados nos dias 1..dia_fim do mês `mes`, por ano, nas células selecionadas."""
    con = duckdb.connect()
    con.register("kt", kt)
    con.register("sel", sel_cells)
    df = con.execute(f"""
        WITH p AS (
            SELECT date, sensor,
                   CAST(floor(longitude / {RES}) AS INT) AS gx,
                   CAST(floor(latitude / {RES}) AS INT) AS gy
            FROM '{PTS}'
            WHERE month(date) = {mes} AND day(date) <= {dia_fim}
              AND ((sensor = 'viirs' AND date >= '{OV_START}')
                OR (sensor = 'modis' AND date <  '{OV_START}')))
        SELECT year(p.date) AS ano,
               SUM(CASE WHEN sensor = 'viirs' THEN 1 ELSE COALESCE(kt.k, {K_DOM}) END) AS H
        FROM p JOIN sel USING (gx, gy) LEFT JOIN kt USING (gx, gy)
        GROUP BY 1""").df()
    return df.set_index("ano").H

def colorir(t, dentro, stops):
    rgb = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in stops])
    pos = np.linspace(0, 1, len(rgb))
    rgba = np.zeros(t.shape + (4,), dtype=np.uint8)
    for ch in range(3):
        rgba[..., ch] = np.interp(t, pos, rgb[:, ch])
    rgba[..., 3] = np.where(dentro & (t > 0.05), 90 + 100 * t, 0).astype(np.uint8)
    return rgba

def validar_coords(la0, la1, lo0, lo1):
    if la0 >= la1:
        return None, "err_lat"
    if lo0 >= lo1:
        return None, "err_lon"
    p = box(lo0, la0, lo1, la1)
    if BR_SHAPE is not None and not p.intersects(BR_SHAPE):
        return None, "err_fora"
    return p, None

def validar_pontos(pts):
    """Monta o polígono a partir dos pontos (lat, lon). Retorna (polígono ou None, chave do erro ou None)."""
    if len(pts) < 3:
        return None, None
    cand = shapely.Polygon([(lo, la) for la, lo in pts])
    if cand.area < 1e-9:
        return None, "poly_linha"
    if not cand.is_valid:
        return None, "poly_cruza"
    if BR_SHAPE is not None and not cand.intersects(BR_SHAPE):
        return None, "err_fora"
    return cand, None

# [upload] leitura do limite da área a partir de um arquivo
@st.cache_data(show_spinner=False)
def ler_area(dados, nome):
    """Lê polígonos de GeoJSON, KML, KMZ ou shapefile (.zip). Retorna (wkt da área ou None, chave do erro ou None)."""
    tag = lambda el: el.tag.rsplit("}", 1)[-1]          # nome da tag sem o namespace do KML

    def anel(el):
        c = next((x for x in el.iter() if tag(x) == "coordinates"), None)
        return [tuple(map(float, p.split(",")[:2])) for p in (c.text or "").split()] if c is not None else []

    try:
        geoms = []
        if nome.endswith((".geojson", ".json")):
            gj = json.loads(dados.decode("utf-8-sig"))
            feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
            for f in feats:
                g = f.get("geometry") if f.get("type") == "Feature" else f
                if g:
                    geoms.append(shape(g))
        elif nome.endswith((".kml", ".kmz")):
            if nome.endswith(".kmz"):
                with zipfile.ZipFile(io.BytesIO(dados)) as z:
                    dados = z.read(next(n for n in z.namelist() if n.lower().endswith(".kml")))
            raiz = ET.fromstring(dados)
            for pg in (el for el in raiz.iter() if tag(el) == "Polygon"):
                ext = next((anel(b) for b in pg if tag(b) == "outerBoundaryIs"), [])
                furos = [r for r in (anel(b) for b in pg if tag(b) == "innerBoundaryIs") if len(r) >= 3]
                if len(ext) >= 3:
                    geoms.append(shapely.Polygon(ext, furos))
        elif nome.endswith(".zip"):
            try:
                import shapefile                                # pacote pyshp
            except ImportError:
                return None, "up_pyshp"
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                nomes = z.namelist()
                base = next(n[:-4] for n in nomes if n.lower().endswith(".shp"))
                parte = lambda ext: io.BytesIO(z.read(next(n for n in nomes if n.lower() == (base + ext).lower())))
                r = shapefile.Reader(shp=parte(".shp"), shx=parte(".shx"), dbf=parte(".dbf"))
                geoms = [shape(s.__geo_interface__) for s in r.shapes() if s.shapeType != shapefile.NULL]
        else:
            return None, "up_tipo"
    except Exception:
        return None, "up_ler"

    # corrige geometrias inválidas e fica só com os polígonos
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return None, "up_vazio"
    partes = shapely.get_parts(shapely.get_parts(shapely.make_valid(np.array(geoms, dtype=object))))
    polys = [p for p in partes if p.geom_type == "Polygon" and not p.is_empty]
    if not polys:
        return None, "up_vazio"
    area = shapely.union_all(polys)
    x0, y0, x1, y1 = area.bounds
    if x0 < -180 or x1 > 180 or y0 < -90 or y1 > 90:
        return None, "up_graus"
    if BR_SHAPE is not None and not area.intersects(BR_SHAPE):
        return None, "err_fora"
    return area.wkt, None

# [temporada] início (10%), fim (90%) e pico a partir das medianas mensais
def temporada(med):
    """Recebe a mediana de cada mês (índice = nomes dos meses). Retorna (início, fim, pico) como índices 0–11."""
    v = med.reindex(MESES).fillna(0).values
    tot = v.sum()
    if tot <= 0:
        return None
    i0 = (int(np.argmin(v)) + 1) % 12                   # conta o ano a partir do mês mais calmo
    ordem = [(i0 + j) % 12 for j in range(12)]
    acum = np.cumsum(v[ordem]) / tot
    ini = ordem[int(np.argmax(acum >= 0.10))]
    fim = ordem[int(np.argmax(acum >= 0.90))]
    return ini, fim, int(np.argmax(v))

def remover_area(ref):
    """[várias áreas] Remove uma área. `ref` = ("user", id) para desenho/coordenadas/arquivo ou ("estado", sigla)."""
    ss = st.session_state
    fonte, ident = ref
    if fonte == "user":
        item = next((x for x in ss.minhas_areas if x["id"] == ident), None)
        if item is None:
            return
        if item["fonte"] == "draw":
            ss.draw_ign.append(item["feat"])           # o mapa ainda devolve o desenho antigo: ignorá-lo
        ss.minhas_areas.remove(item)
    elif fonte == "estado":
        atual = [u for u in ss.get("uf_multi", []) if u != ident]
        ss.uf_pend = atual                             # aplicado antes de o seletor ser desenhado

# ---------------- barra lateral
with st.sidebar:
    # ⚙ Configurações (idioma e tema)
    cfg = st.popover(":material/settings:", help="Configurações · Settings")
    with cfg:
        lang = st.radio("Language · Idioma", ["EN", "PT"], horizontal=True)
        T = TXT[lang]
        tema = st.radio(T["tema"], ["light", "dark"], format_func=lambda k: T[k], horizontal=True)
    MESES = T["meses"]
    fmt_ts = lambda t: f"{MESES[t.month - 1]}/{t.year}"
    ss = st.session_state

    st.markdown(f'<div class="side-brand" style="margin-top:14px">{T["filtros"]}</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="sec">{T["area"]}</div>', unsafe_allow_html=True)
    for k, v in [("minhas_areas", []), ("draw_ign", []), ("coord_pts", []), ("up_key", 0), ("area_seq", 0)]:
        ss.setdefault(k, v)
    areas, refs = [], []                               # [várias áreas] (nome, geometria) e referência de cada uma

    def nova_area(fonte, nome, wkt, feat=None):
        ss.area_seq += 1
        ss.minhas_areas.append(dict(id=ss.area_seq, fonte=fonte, nome=nome or f"{T['nome_' + fonte]} {ss.area_seq}",
                                    wkt=wkt, feat=feat))

    pais = st.toggle(T["pais"], key="modo_pais")                               # [país] exclusivo
    usa = {}
    if pais:
        if BR_SHAPE is not None:
            areas, refs = [(T["brasil"], BR_SHAPE)], [("pais", None)]
        st.caption(T["pais_hint"])
    else:
        st.caption(T["fontes_hint"])
        for k in ("draw", "coords", "upload", "estado"):                       # fontes combináveis
            usa[k] = st.checkbox(T[k], value=(k == "draw"), key=f"usa_{k}")

            if not usa[k]:
                continue
            caixa = st.container(border=True)
            with caixa:
                if k == "draw":
                    st.caption(T["draw_hint"])

                elif k == "coords":
                    with st.form("form_ponto", clear_on_submit=False, border=False):
                        c1, c2 = st.columns(2)
                        p_lat = c1.number_input(T["lat"], value=-15.0, min_value=-90.0, max_value=90.0,
                                                step=0.5, format="%.4f")
                        p_lon = c2.number_input(T["lon"], value=-50.0, min_value=-180.0, max_value=180.0,
                                                step=0.5, format="%.4f")
                        add = st.form_submit_button(T["add_pt"], use_container_width=True)
                    if add:
                        pt = (round(float(p_lat), 4), round(float(p_lon), 4))
                        if not (SA["min_lat"] <= pt[0] <= SA["max_lat"] and SA["min_lon"] <= pt[1] <= SA["max_lon"]):
                            st.error(T["pt_fora"], icon=":material/error:")
                        elif pt in ss.coord_pts:
                            st.error(T["pt_dup"], icon=":material/error:")
                        else:
                            ss.coord_pts.append(pt)
                    pts_sel = ss.coord_pts
                    if pts_sel:
                        st.markdown(f'<div class="sec-sub">{T["pts_titulo"]} ({len(pts_sel)})</div>',
                                    unsafe_allow_html=True)
                        for i, (la, lo) in enumerate(pts_sel):
                            r1, r2 = st.columns([5, 1])
                            r1.markdown(f'<div class="pt-item"><b>P{i + 1}</b>&nbsp; {la:.4f}, {lo:.4f}</div>',
                                        unsafe_allow_html=True)
                            if r2.button("✕", key=f"rm_pt_{i}", help=T["rm_pt"]):
                                pts_sel.pop(i)
                                st.rerun()
                    cand, erro_pts = validar_pontos(pts_sel)
                    if len(pts_sel) < 3:
                        st.caption(T["pt_min"].format(n=len(pts_sel)))
                    elif erro_pts:
                        st.error(T[erro_pts], icon=":material/error:")
                    if ss.pop("coord_nome_reset", False):
                        ss.coord_nome = ""
                    nome_c = st.text_input(T["nome_area"], key="coord_nome", placeholder=T["nome_coords"],
                                           disabled=cand is None)
                    b1, b2 = st.columns(2)
                    if b1.button(T["concluir"], use_container_width=True, disabled=cand is None, type="primary"):
                        nova_area("coords", nome_c.strip(), cand.wkt)
                        ss.coord_pts = []
                        ss.coord_nome_reset = True
                        st.rerun()
                    if b2.button(T["limpar_pts"], use_container_width=True, disabled=not pts_sel):
                        ss.coord_pts = []
                        st.rerun()

                elif k == "upload":                                            # [upload] vários arquivos
                    for e in ss.pop("up_erros", []):
                        st.error(e, icon=":material/error:")
                    arqs = st.file_uploader(T["up_lbl"], type=["kml", "kmz", "geojson", "json", "zip"],
                                            accept_multiple_files=True, key=f"up_{ss.up_key}")
                    st.caption(T["up_hint"])
                    if arqs:                                   # cada arquivo vira uma área; o campo é esvaziado
                        erros = []
                        for arq in arqs:
                            wkt_up, erro_up = ler_area(arq.getvalue(), arq.name.lower())
                            if erro_up:
                                erros.append(f"{arq.name}: {T[erro_up]}")
                            elif not any(x["wkt"] == wkt_up for x in ss.minhas_areas):
                                nova_area("upload", os.path.splitext(arq.name)[0], wkt_up)
                        ss.up_erros = erros
                        ss.up_key += 1
                        st.rerun()

                else:                                                          # [estado] vários estados
                    with st.spinner():
                        ufs = estados()
                    if not ufs:
                        st.error(T["uf_err"], icon=":material/error:")
                    else:
                        if "uf_pend" in ss:                    # remoção feita pelo ✕ do mapa
                            ss.uf_multi = ss.pop("uf_pend")
                        ufs_sel = st.multiselect(T["uf_lbl"], sorted(ufs, key=UF_NOME.get), key="uf_multi",
                                                 format_func=lambda s: f"{UF_NOME[s]} ({s})",
                                                 placeholder=T["uf_ph"], label_visibility="collapsed")
                        areas += [(UF_NOME[s], shapely.from_wkt(ufs[s])) for s in ufs_sel]
                        refs += [("estado", s) for s in ufs_sel]

        # [várias áreas] suas áreas (desenho, coordenadas, arquivo): nome editável + ✕
        ICONE = {"draw": ":material/draw:", "coords": ":material/location_on:", "upload": ":material/upload_file:"}
        minhas = [x for x in ss.minhas_areas if usa.get(x["fonte"])]
        if minhas:
            st.markdown(f'<div class="sec-sub">{T["areas_titulo"]}</div>', unsafe_allow_html=True)
            for x in minhas:
                r0, r1, r2 = st.columns([1, 6, 1.4], vertical_alignment="center")
                r0.markdown(ICONE[x["fonte"]])
                novo = r1.text_input(T["nome_lbl"], value=x["nome"], key=f"nome_{x['id']}",
                                     label_visibility="collapsed")
                x["nome"] = novo.strip() or f"{T['nome_' + x['fonte']]} {x['id']}"
                if r2.button("✕", key=f"rm_area_{x['id']}", help=T["rm_area"]):
                    remover_area(("user", x["id"]))
                    st.rerun()
                areas.append((x["nome"], shape(x["feat"]["geometry"]) if x["fonte"] == "draw"
                              else shapely.from_wkt(x["wkt"])))
                refs.append(("user", x["id"]))
            if st.button(T["limpar_areas"], use_container_width=True, key="limpar_areas"):
                for x in minhas:
                    remover_area(("user", x["id"]))
                st.rerun()
        if any(x["fonte"] in usa and not usa[x["fonte"]] for x in ss.minhas_areas):
            st.caption(T["fonte_off"])

    poly_sel = shapely.union_all([g for _, g in areas]) if areas else None    # união, para as análises

    # [tempo real] [alertas] opções dentro de ⚙ Configurações
    with cfg:
        st.divider()
        intervalo = st.selectbox(T["rt_intervalo"], INTERVALOS, index=INTERVALOS.index(15),
                                 format_func=lambda m: f"{m} min", key="rt_int", help=T["rt_int_help"])
        st.markdown(f"**{T['al_titulo']}**")
        alertas_on = st.toggle(T["al_on"], key="al_on")
        st.caption(T["al_hint"])

    # período: De (mês + ano) / Até (mês + ano) — "Até" só oferece datas a partir de "De"
    st.markdown(f'<div class="sec">{T["periodo"]}</div>', unsafe_allow_html=True)
    ANO0, ANO1 = DADOS_INI.year, ULT_MES.year

    def faixa_meses(ano, minimo=1):
        """Meses disponíveis no ano (respeita o início dos dados, o último mês com dados e um mínimo)."""
        lo = max(minimo, DADOS_INI.month if ano == ANO0 else 1)
        hi = ULT_MES.month if ano == ANO1 else 12
        return list(range(lo, hi + 1))

    def fixar(key, opcoes, padrao):
        """Garante que o valor guardado do seletor esteja entre as opções válidas (ajusta para o mais próximo)."""
        v = ss.get(key, padrao)
        ss[key] = min(max(v, opcoes[0]), opcoes[-1])

    st.markdown(f'<div class="sec-sub">{T["de"]}</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([3, 2])
    anos_de = list(range(ANO0, ANO1 + 1))
    fixar("a_ini", anos_de, ANO_BASE)
    a_ini = c2.selectbox(T["ano"], anos_de, key="a_ini", label_visibility="collapsed")
    meses_de = faixa_meses(a_ini)
    fixar("m_ini", meses_de, 1)
    m_ini = c1.selectbox(T["mes"], meses_de, format_func=lambda i: MESES[i - 1],
                         key="m_ini", label_visibility="collapsed")

    st.markdown(f'<div class="sec-sub">{T["ate"]}</div>', unsafe_allow_html=True)
    c3, c4 = st.columns([3, 2])
    anos_ate = list(range(a_ini, ANO1 + 1))
    fixar("a_fim", anos_ate, ANO1)
    a_fim = c4.selectbox(T["ano"], anos_ate, key="a_fim", label_visibility="collapsed")
    meses_ate = faixa_meses(a_fim, m_ini if a_fim == a_ini else 1)
    fixar("m_fim", meses_ate, ULT_MES.month)
    m_fim = c3.selectbox(T["mes"], meses_ate, format_func=lambda i: MESES[i - 1],
                         key="m_fim", label_visibility="collapsed")

    INI = pd.Timestamp(year=a_ini, month=m_ini, day=1)
    FIM = pd.Timestamp(year=a_fim, month=m_fim, day=1)
    if INI > FIM:
        INI, FIM = FIM, INI
        st.warning(T["err_periodo"], icon=":material/swap_horiz:")
    INI_c, FIM_c = max(INI, DADOS_INI), min(FIM, ULT_MES)
    if (INI_c, FIM_c) != (INI, FIM):
        st.caption(T["ajuste"])
    INI, FIM = INI_c, FIM_c
    st.caption(T["per_hint"] + " " + T["disp"].format(a=fmt_ts(DADOS_INI), b=fmt_ts(ULT_MES))
               + " " + T["aviso_2000"])

    st.markdown(f'<div class="sec">{T["info"]}</div>', unsafe_allow_html=True)
    with st.expander(T["acess"]):
        st.markdown(T["acess_txt"])
    with st.expander(T["sobre"]):
        st.markdown(T["sobre_txt"])

    st.markdown(f'<div class="resize-hint">{T["resize_hint"]}</div>', unsafe_allow_html=True)

# [alertas] estado da sessão: histórico, focos já vistos e avisos pendentes
if "hist" not in ss:
    ss.hist = carregar_hist()
    ss.vistos = set(zip(ss.hist.area.astype(str), ss.hist.id.astype(str)))
ss.setdefault("toasts", [])
for msg in ss.toasts:
    st.toast(msg, icon="🔥")
ss.toasts = []

FIM_EXCL = FIM + pd.offsets.MonthBegin(1)
N_MESES = (FIM.year - INI.year) * 12 + (FIM.month - INI.month) + 1

P = TEMAS[tema]
ESCURO = tema == "dark"
CORES = {T["s_modis"]: "#E69F00", T["s_viirs"]: "#0072B2", T["s_harm"]: P["harm"],
         T["s_real"]: "#0072B2", T["s_prev"]: "#D55E00"}                       # Okabe-Ito

# ---------------- estilo da página (variáveis do tema + regras)
st.markdown(f"<style>:root {{ {' '.join(f'--{k}: {v};' for k, v in P.items() if isinstance(v, str))} }}</style>",
            unsafe_allow_html=True)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, .stApp, p, li, label, input, textarea, button, h1, h2, h3, h4,
[data-testid="stMarkdownContainer"], [data-testid="stMetricValue"],
[data-testid="stMetricLabel"], [data-testid="stMetricDelta"], [data-testid="stCaptionContainer"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}
#MainMenu, footer { visibility: hidden; }
.stApp { background: var(--bg); }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.4rem; padding-bottom: 2rem; max-width: 100%; }

[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stWidgetLabel"] p, .stApp label { color: var(--text2); }
[data-testid="stMarkdownContainer"] strong { color: var(--text); }
[data-testid="stCaptionContainer"] p { color: var(--muted) !important; font-size: .78rem; }
[data-testid="stMetricDelta"] p { color: inherit !important; }

[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }
[data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"] { color: var(--muted); }
[data-testid="stSidebar"] [data-testid="stAlert"] p { font-size: .8rem; }

/* botão de configurações (engrenagem) e painel */
[data-testid="stPopover"] button { background: var(--surface); color: var(--text2); border: 1px solid var(--border);
                                   border-radius: 6px; box-shadow: none; padding: 4px 10px; }
[data-testid="stPopover"] button:hover { border-color: var(--accent); color: var(--accent); }
[data-testid="stPopoverBody"] { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }

/* ícone de ajuda: "i" em vez de "?" — só nos títulos dos indicadores e rótulos de campos (botões não) */
[data-testid="stMetricLabel"] [data-testid="stTooltipHoverTarget"] svg,
[data-testid="stWidgetLabel"] [data-testid="stTooltipHoverTarget"] svg,
[data-testid="stMetricLabel"] [data-testid="stTooltipIcon"] svg,
[data-testid="stWidgetLabel"] [data-testid="stTooltipIcon"] svg { display: none !important; }
[data-testid="stMetricLabel"] [data-testid="stTooltipHoverTarget"]::before,
[data-testid="stWidgetLabel"] [data-testid="stTooltipHoverTarget"]::before {
    content: "i"; display: inline-flex; align-items: center; justify-content: center;
    width: 15px; height: 15px; border-radius: 50%; border: 1.3px solid var(--muted); color: var(--muted);
    font: italic 600 10px/1 Georgia, 'Times New Roman', serif; cursor: help; margin-left: 4px; }
[data-testid="stMetricLabel"] [data-testid="stTooltipHoverTarget"]:hover::before,
[data-testid="stWidgetLabel"] [data-testid="stTooltipHoverTarget"]:hover::before {
    border-color: var(--accent); color: var(--accent); }
[data-baseweb="tooltip"] { max-width: 320px !important; }

/* balões de dica: seguem o tema */
[data-baseweb="tooltip"], [data-testid="stTooltipContent"] {
    background: var(--surface) !important; border: 1px solid var(--border) !important;
    border-radius: 6px !important; box-shadow: 0 2px 8px rgba(0,0,0,.08) !important; }
[data-baseweb="tooltip"] *, [data-testid="stTooltipContent"] * {
    background: transparent !important; color: var(--text) !important; }
[data-baseweb="tooltip"] p, [data-testid="stTooltipContent"] p { font-size: .78rem; }

[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div,
[data-testid="stNumberInput"] input { background: var(--input) !important; color: var(--text) !important;
                                       border-color: var(--border) !important; }
[data-testid="stNumberInput"] button { background: var(--input); color: var(--text2); }

/* campos numéricos (lat/lon) e de texto (nomes): uma única borda fina, sem a borda grossa interna */
[data-testid="stTextInputRootElement"] {
    border: 1px solid var(--border) !important; border-radius: 6px !important;
    background: var(--input) !important; box-shadow: none !important; overflow: hidden; }
[data-testid="stTextInputRootElement"]:focus-within { border-color: var(--accent) !important; }
[data-testid="stTextInputRootElement"] [data-baseweb="input"],
[data-testid="stTextInputRootElement"] [data-baseweb="base-input"],
[data-testid="stTextInput"] input {
    border: none !important; border-radius: 0 !important; box-shadow: none !important; outline: none !important; }
/* cor do texto digitado e do texto de exemplo seguem o tema (também com o campo desabilitado) */
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {
    color: var(--text) !important; -webkit-text-fill-color: var(--text) !important; }
[data-testid="stTextInput"] input::placeholder, [data-testid="stNumberInput"] input::placeholder {
    color: var(--muted) !important; -webkit-text-fill-color: var(--muted) !important; opacity: 1 !important; }
[data-testid="stTextInput"] input:disabled { opacity: .6; }
[data-testid="stNumberInputContainer"] {
    border: 1px solid var(--border) !important; border-radius: 6px !important;
    background: var(--input) !important; box-shadow: none !important; overflow: hidden; }
[data-testid="stNumberInputContainer"]:focus-within { border-color: var(--accent) !important; }
[data-testid="stNumberInputContainer"] [data-baseweb="input"],
[data-testid="stNumberInputContainer"] [data-baseweb="base-input"],
[data-testid="stNumberInput"] input {
    border: none !important; border-radius: 0 !important; box-shadow: none !important; outline: none !important; }
[data-testid="stNumberInput"] button { border: none !important; box-shadow: none !important; }
[data-testid="stNumberInput"] button:hover { background: var(--hover) !important; color: var(--accent) !important; }
[data-baseweb="popover"] ul, [data-baseweb="menu"] { background: var(--surface) !important; }
[data-baseweb="popover"] li { color: var(--text) !important; }

.stButton button, .stDownloadButton button { background: var(--surface); color: var(--text);
    border: 1px solid var(--border); border-radius: 6px; box-shadow: none; font-weight: 500; }
.stButton button:hover, .stDownloadButton button:hover { border-color: var(--accent); color: var(--accent); }
.stButton button[kind="primary"] { background: var(--accent); border-color: var(--accent); color: #FFFFFF; }
.stButton button[kind="primary"]:hover { filter: brightness(1.08); color: #FFFFFF; }
.stButton button[kind="primary"]:disabled { background: var(--surface); border-color: var(--border); color: var(--muted); filter: none; }
/* caixas, chaves e opções marcadas em verde (complementa o primaryColor do config.toml) */
[data-testid="stCheckbox"] [data-baseweb="checkbox"] input:checked + div,
[data-baseweb="checkbox"] [aria-checked="true"] { background-color: var(--accent) !important; border-color: var(--accent) !important; }
[data-baseweb="radio"] input:checked + div { background-color: var(--accent) !important; border-color: var(--accent) !important; }
[data-baseweb="tag"] { background: var(--accent_bg) !important; color: var(--accent) !important; }
[data-baseweb="tag"] * { color: var(--accent) !important; }
[data-testid="stExpander"] details { background: var(--surface); border: 1px solid var(--border);
                                     border-radius: 8px; box-shadow: none; }
[data-testid="stExpander"] summary p { color: var(--text) !important; font-weight: 500; }
[data-testid="stExpander"] summary svg { color: var(--muted); }

/* formulário e lista de pontos das coordenadas */
[data-testid="stSidebar"] [data-testid="stForm"] { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
[data-testid="stFormSubmitButton"] button { background: var(--surface); color: var(--text);
    border: 1px solid var(--border); border-radius: 6px; box-shadow: none; font-weight: 500; }
[data-testid="stFormSubmitButton"] button:hover { border-color: var(--accent); color: var(--accent); }
.pt-item { font-size: .8rem; color: var(--text2); padding-top: 8px; font-feature-settings: "tnum"; }
.pt-item b { color: var(--text); }

/* [upload] caixa de envio e arquivo enviado: seguem o tema (nada de fundo preto) */
[data-testid="stFileUploader"] * { background-color: transparent !important; }
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
    background: var(--input) !important; border: 1px dashed var(--border) !important; border-radius: 8px !important; }
[data-testid="stFileUploaderDropzone"] * { color: var(--text2) !important; }
/* texto da caixa de envio quebra linha em vez de cortar com reticências ao redimensionar a barra */
[data-testid="stFileUploaderDropzone"] { flex-wrap: wrap !important; gap: 8px !important; height: auto !important; }
[data-testid="stFileUploaderDropzoneInstructions"] { min-width: 0 !important; flex: 1 1 120px !important; }
[data-testid="stFileUploaderDropzoneInstructions"] * {
    white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
    overflow-wrap: anywhere !important; max-width: 100% !important; }
[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] {
    background: var(--surface) !important; border: 1px solid var(--border) !important;
    border-radius: 8px !important; padding: 6px 8px !important; }
[data-testid="stFileUploaderFile"] * { color: var(--text) !important; }
[data-testid="stFileUploaderFile"] small { color: var(--muted) !important; }
[data-testid="stFileUploaderFile"] svg { color: var(--muted) !important; }
[data-testid="stFileUploader"] button { background: var(--surface) !important; color: var(--text2) !important;
    border: 1px solid var(--border) !important; border-radius: 6px !important; box-shadow: none !important; }
[data-testid="stFileUploader"] button:hover { border-color: var(--accent) !important; color: var(--accent) !important; }
[data-testid="stFileUploaderDeleteBtn"] button { border: none !important; background: transparent !important; }
[data-testid="stFileUploaderDeleteBtn"] button:hover { color: var(--danger) !important; }

/* avisos (preenchimento inválido, sem dados): vermelho clarinho */
[data-testid="stAlert"] > div, [data-testid="stAlert"] [data-baseweb="notification"] {
    background: var(--danger_bg) !important; border: 1px solid var(--danger) !important;
    border-radius: 8px !important; box-shadow: none !important; }
[data-testid="stAlert"] [data-testid="stAlertContainer"] { background: transparent !important; border: none !important; }
[data-testid="stAlert"] p, [data-testid="stAlert"] svg,
[data-testid="stAlert"] [data-testid="stIconMaterial"] { color: var(--danger) !important; fill: var(--danger) !important; }

/* alça visual de redimensionamento na borda direita da barra lateral */
section[data-testid="stSidebar"]::after {
    content: ""; position: absolute; top: 50%; right: 3px; transform: translateY(-50%);
    width: 8px; height: 44px; border-radius: 4px; pointer-events: none; z-index: 1000;
    background-image: radial-gradient(circle, var(--muted) 1.3px, transparent 1.7px);
    background-size: 4px 6px;
}
.resize-hint { font-size: .74rem; color: var(--muted); margin-top: 28px; padding-top: 10px;
               border-top: 1px solid var(--border); }

.side-brand { font-size: .95rem; font-weight: 600; color: var(--text); margin-bottom: 4px; }
.sec { font-size: .7rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted);
       font-weight: 600; margin: 20px 0 6px; }
.sec-sub { font-size: .76rem; color: var(--text2); font-weight: 500; margin: 6px 0 2px; }

.app-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px;
              padding-bottom: 14px; border-bottom: 1px solid var(--border); margin-bottom: 16px; flex-wrap: wrap;
              position: relative; }
/* identidade: traço verde + ouro sob o cabeçalho */
.app-header::after { content: ""; position: absolute; left: 0; bottom: -2px; width: 64px; height: 3px;
                     border-radius: 2px; background: linear-gradient(90deg, var(--accent) 0 60%, var(--gold) 60% 100%); }
.eyebrow { color: var(--accent) !important; }
.app-header h1 { font-size: 1.45rem; font-weight: 600; letter-spacing: -0.01em; color: var(--text);
                 margin: 2px 0; padding: 0; }
.eyebrow { font-size: .7rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 500; }
.sub { font-size: .88rem; color: var(--text2); margin: 0; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { font-size: .76rem; color: var(--text2); background: var(--surface); border: 1px solid var(--border);
        border-radius: 999px; padding: 4px 10px; white-space: nowrap; }

[data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
                           padding: 12px 16px; height: 100%; }
[data-testid="stMetricLabel"] p { font-size: .76rem; color: var(--muted) !important; font-weight: 500; }
[data-testid="stMetricValue"] { font-size: 1.3rem; font-weight: 600; color: var(--text); font-feature-settings: "tnum"; }
/* selo de variação: formato de pílula; a cor é definida pelo sinal no bloco dos indicadores */
[data-testid="stMetricDelta"] { border-radius: 999px; padding: 1px 8px; width: fit-content; }
/* esconde o ícone do Streamlit (aparecia como quadrado); a seta vai no próprio texto */
[data-testid="stMetricDelta"] svg,
[data-testid="stMetricDelta"] [data-testid="stIconMaterial"],
[data-testid="stMetricDelta"] [data-testid^="stMetricDeltaIcon"] { display: none !important; }

iframe[title="streamlit_folium.st_folium"] { border: 1px solid var(--border); border-radius: 8px; }

.legend { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; padding: 8px 2px 4px;
          font-size: .78rem; color: var(--text2); }
.legend-title { font-weight: 600; color: var(--text); }
.legend-scale { display: flex; align-items: center; gap: 8px; }
.legend-bar { width: 180px; height: 8px; border-radius: 2px; }
.legend-note { color: var(--muted); }
.legend-swatch { display: inline-block; width: 14px; height: 10px; border-radius: 2px;
                 background: var(--mask); opacity: .7; vertical-align: middle; margin-right: 6px;
                 border: 1px solid var(--border); }

.comp-title { font-size: .95rem; font-weight: 600; color: var(--text); margin: 4px 0 0; }

.stTabs [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] { padding: 8px 14px; }
.stTabs [data-baseweb="tab"] p { font-size: .86rem; font-weight: 500; color: var(--muted); }
.stTabs [aria-selected="true"] p { color: var(--text); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--gold); height: 3px; }
.stTabs [aria-selected="true"] p { color: var(--accent) !important; font-weight: 600; }
.stTabs [data-baseweb="tab-border"] { background: var(--border); }
</style>
""", unsafe_allow_html=True)

# ---------------- estilo dentro do mapa (o mapa roda num iframe próprio)
ICO_POLY = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
            "<path d='M5 8l7-4 7 5-2 9H7z' fill='%233388ff' fill-opacity='.18' stroke='%23374151' "
            "stroke-width='1.8' stroke-linejoin='round'/><g fill='%23ffffff' stroke='%23374151' stroke-width='1.5'>"
            "<circle cx='5' cy='8' r='1.9'/><circle cx='12' cy='4' r='1.9'/><circle cx='19' cy='9' r='1.9'/>"
            "<circle cx='17' cy='18' r='1.9'/><circle cx='7' cy='18' r='1.9'/></g></svg>")
ICO_RECT = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
            "<rect x='4' y='6' width='16' height='12' fill='%233388ff' fill-opacity='.18' stroke='%23374151' "
            "stroke-width='1.8' stroke-dasharray='3 2'/><g fill='%23ffffff' stroke='%23374151' stroke-width='1.5'>"
            "<circle cx='4' cy='6' r='1.9'/><circle cx='20' cy='18' r='1.9'/></g></svg>")
MAP_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
.leaflet-container {{ font-family: 'Inter', system-ui, sans-serif; background: {P['leaflet_bg']}; }}
.leaflet-bar {{ border: 1px solid #D1D5DB !important; box-shadow: none !important; border-radius: 6px !important; overflow: hidden; }}
.leaflet-bar a {{ color: #374151 !important; border-bottom: 1px solid #E5E7EB !important; }}
.leaflet-bar a:hover {{ background: #F9FAFB !important; }}
.leaflet-control-layers {{ border: 1px solid #D1D5DB !important; box-shadow: none !important; border-radius: 6px !important;
                          font-size: 12px; color: #374151; }}
.leaflet-control-layers-expanded {{ padding: 8px 12px; }}
.leaflet-control-layers-separator {{ border-top: 1px solid #E5E7EB; }}
.leaflet-control-scale-line {{ border-color: #6B7280; color: #374151; background: rgba(255,255,255,.85); font-size: 11px; }}
.leaflet-control-attribution {{ font-size: 10px; background: rgba(255,255,255,.75) !important; }}
.leaflet-draw-tooltip {{ font-family: 'Inter', sans-serif; font-size: 11px; }}
/* vértices como pontos pequenos em vez de quadrados grandes */
.leaflet-editing-icon, .leaflet-touch .leaflet-editing-icon {{
    width: 10px !important; height: 10px !important;
    margin-left: -5px !important; margin-top: -5px !important;
    border-radius: 50% !important; border: 2px solid #3388ff !important;
    background: #ffffff !important; box-shadow: none !important; }}
.leaflet-draw-actions a {{ font-family: 'Inter', sans-serif; font-size: 12px; }}
/* ferramentas de desenho: ícone + rótulo dentro do mesmo botão */
.leaflet-draw-toolbar a.leaflet-draw-draw-polygon,
.leaflet-draw-toolbar a.leaflet-draw-draw-rectangle {{
    width: auto !important; min-width: 30px; display: flex !important; align-items: center;
    padding: 0 10px 0 32px !important; white-space: nowrap; text-decoration: none;
    background-position: 7px center !important; background-size: 18px 18px !important;
    background-repeat: no-repeat !important; background-color: #ffffff; }}
.leaflet-draw-toolbar a.leaflet-draw-draw-polygon {{ background-image: url("{ICO_POLY}") !important; }}
.leaflet-draw-toolbar a.leaflet-draw-draw-rectangle {{ background-image: url("{ICO_RECT}") !important; }}
.leaflet-draw-toolbar a.leaflet-draw-draw-polygon::after,
.leaflet-draw-toolbar a.leaflet-draw-draw-rectangle::after {{
    font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 500; color: #374151; }}
.leaflet-draw-toolbar a.leaflet-draw-draw-polygon::after {{ content: "{DRAW_TXT[lang]['lbl_poly']}"; }}
.leaflet-draw-toolbar a.leaflet-draw-draw-rectangle::after {{ content: "{DRAW_TXT[lang]['lbl_rect']}"; }}
.leaflet-draw-toolbar a.leaflet-draw-toolbar-button-enabled {{ background-color: #EAF2FF !important; }}
.leaflet-draw-toolbar a.leaflet-draw-toolbar-button-enabled::after {{ color: #1D4ED8; }}
/* botões Cancelar/Concluir aparecem à direita da barra (agora mais larga) */
.leaflet-draw-actions, .leaflet-touch .leaflet-draw-actions {{ left: calc(100% + 6px) !important; }}
/* [remover área] botão ✕ e modo remover */
.rm-ctl a.rm-btn {{ font-size: 14px; font-weight: 700; text-decoration: none; }}
.rm-ctl a.rm-btn.ativo {{ background: #FDECEA !important; color: #B42318 !important; }}
.rm-ctl.vazio a.rm-btn {{ color: #C0C4CA !important; cursor: not-allowed; }}
.rm-ctl.vazio a.rm-btn:hover {{ background: #ffffff !important; }}
.leaflet-container.modo-rm {{ cursor: crosshair; }}
</style>
"""

PLOT_CFG = {"displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2}}

def estilo(fig, altura=380, grade=True):
    fig.update_layout(height=altura, margin=dict(l=64, r=24, t=40, b=56),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter, system-ui, sans-serif", size=12, color=P["text2"]),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None,
                                  font=dict(color=P["text2"])),
                      hoverlabel=dict(bgcolor=P["surface"], bordercolor=P["border"],
                                      font=dict(family="Inter, system-ui, sans-serif", color=P["text"])),
                      modebar=dict(bgcolor="rgba(0,0,0,0)", color=P["muted"], activecolor=P["text"]),
                      coloraxis_colorbar=dict(tickfont=dict(color=P["text2"]),
                                              title=dict(side="right", font=dict(color=P["text2"]))))
    eixo = dict(showgrid=grade, gridcolor=P["grid"], linecolor=P["border"], zeroline=False,
                tickfont=dict(color=P["text2"]), title_font=dict(color=P["text2"]),
                automargin=True, title_standoff=12, ticks="outside", ticklen=4, tickcolor=P["border"])
    fig.update_xaxes(**eixo)
    fig.update_yaxes(**eixo)
    return fig

def travar_zoom(fig, df):
    """Permite aproximar, mas não afastar além da visão inicial."""
    fig.update_xaxes(minallowed=-0.5, maxallowed=len(df.columns) - 0.5)
    fig.update_yaxes(minallowed=df.index.min() - 0.5, maxallowed=df.index.max() + 0.5)
    return fig

# ---------------- cabeçalho
nomes_areas = [n for n, _ in areas]
area_txt = (T["area_br"] if not areas else
            T["area_lbl"].format(a=", ".join(nomes_areas)) if len(areas) <= 3 else
            T["area_n_lbl"].format(n=len(areas)))

# [alertas] cada área de interesse é monitorada separadamente: (nome, wkt)
alert_areas = [(n, g.wkt) for n, g in areas] if alertas_on else []
chip_al = f'<span class="chip">{T["al_chip"].format(n=len(alert_areas))}</span>' if alert_areas else ""

st.markdown(f"""
<div class="app-header">
  <div>
    <div class="eyebrow">{T["eyebrow"]}</div>
    <h1>{T["titulo"]}</h1>
    <p class="sub">{T["sub"]}</p>
  </div>
  <div class="chips">
    <span class="chip">{T["dados_ate"]} {ULT.day} {MESES[ULT.month - 1]}/{ULT.year}</span>
    <span class="chip">{area_txt}</span>
    <span class="chip">{T["periodo"]}: {fmt_ts(INI)} – {fmt_ts(FIM)}</span>
    {chip_al}
  </div>
</div>
""", unsafe_allow_html=True)

kpi_box = st.container()          # preenchido depois do mapa

# ---------------- mapa (restrito à América do Sul)
m = folium.Map(location=[-15, -55], zoom_start=4, tiles=None, control_scale=True,
               min_zoom=3, max_bounds=True, **SA)
m.get_root().header.add_child(folium.Element(MAP_CSS))
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer(ESRI_IMG, attr=ESRI_ATTR, name=T["l_sat"], show=False, max_zoom=19).add_to(m)
folium.map.CustomPane("rotulos", z_index=650).add_to(m)

if fora_br is not None:
    folium.GeoJson(fora_br, name=T["l_fora"], interactive=False,
                   style_function=lambda f: {"fillColor": P["mask"], "fillOpacity": P["mask_op"],
                                             "color": P["mask"], "weight": 0}).add_to(m)
    folium.GeoJson(contorno_br, name=T["l_limite"], interactive=False, control=False,
                   style_function=lambda f: {"fill": False, "color": P["muted"], "weight": 1}).add_to(m)

tem_raster = False
sel_layers = []                                      # [remover área] uma camada por área
# [várias áreas] uma imagem por área, com a mesma escala de cor para todas
if areas:
    with st.spinner(T["gerando"]):
        rs = [raster(g.wkt, INI.strftime("%Y-%m-%d"), FIM_EXCL.strftime("%Y-%m-%d"), N_MESES) for _, g in areas]
    rs = [r for r in rs if r is not None]
    if rs:
        q = np.quantile(np.concatenate([v[dn & (v > 0)] for v, dn, _ in rs]), 0.99)
        for v, dn, bounds in rs:
            folium.raster_layers.ImageOverlay(colorir(np.clip(v / q, 0, 1), dn, PAL), bounds=bounds,
                                              origin="lower", pixelated=False, name=T["l_focos"]).add_to(m)
        tem_raster = True
if areas and not pais:
    # [remover área] preenchimento invisível para o clique valer na área toda
    for nome, g in areas:
        lyr = folium.GeoJson(mapping(g), name=f'{T["l_sel"]}: {nome}', tooltip=nome,
                             style_function=lambda f: {"color": P["text"], "weight": 1.5, "fill": True,
                                                       "fillOpacity": 0, "dashArray": "5,5"})
        lyr.add_to(m)
        sel_layers.append(lyr)
    x0, y0, x1, y1 = poly_sel.bounds
    m.fit_bounds([[y0, x0], [y1, x1]])

# pontos da área em construção (coordenadas): bolinhas + linha tracejada até fechar a área
if usa.get("coords") and ss.coord_pts:
    pts_ll = list(ss.coord_pts)
    if len(pts_ll) >= 2:
        linha = pts_ll + ([pts_ll[0]] if len(pts_ll) >= 3 else [])
        folium.PolyLine(linha, color="#3388ff", weight=2, dash_array="4,4").add_to(m)
    for i, (la, lo) in enumerate(pts_ll, 1):
        folium.CircleMarker((la, lo), radius=4, color="#3388ff", weight=2, fill=True,
                            fill_color="#ffffff", fill_opacity=1,
                            tooltip=f"P{i}: {la:.4f}, {lo:.4f}").add_to(m)
    las, los = [p[0] for p in pts_ll], [p[1] for p in pts_ll]
    if poly_sel is not None:
        x0, y0, x1, y1 = poly_sel.bounds
        las, los = las + [y0, y1], los + [x0, x1]
    m.fit_bounds([[min(las) - 1, min(los) - 1], [max(las) + 1, max(los) + 1]])

folium.TileLayer(DARK_LABELS if ESCURO else LIGHT_LABELS, attr=LABELS_ATTR, name=T["l_rot"],
                 max_native_zoom=16, max_zoom=19, overlay=True, pane="rotulos", show=False).add_to(m)
if usa.get("draw"):
    JsSnippet(draw_i18n_js(lang)).add_to(m)          # textos no idioma escolhido (antes de criar o Draw)
    Draw(export=False, position="topleft",
         draw_options={"polyline": False, "circle": False, "marker": False, "circlemarker": False},
         edit_options={"edit": False, "remove": False}).add_to(m)
# [remover área] botão ✕ abaixo das ferramentas de desenho (em todos os modos)
JsSnippet(rm_ctl_js(m.get_name(), [l.get_name() for l in sel_layers],
                    dict(btn=T["rm_btn"], tip=T["rm_tip"], vazio=T["rm_vazio"],
                         cor=P["danger"], base=P["text"]))).add_to(m)
folium.LayerControl(position="topright", collapsed=True).add_to(m)

out = st_folium(m, key="mapa", height=600, use_container_width=True,
                returned_objects=["last_active_drawing", "last_object_clicked"])   # [remover área]

# [remover área] sinal de remoção vindo do mapa (clique numa latitude impossível; o índice vem na latitude)
clique = (out or {}).get("last_object_clicked")
if (sel_layers and clique and -90 < clique.get("lat", 0) < RM_LAT + RM_PASSO / 2
        and clique != ss.get("clique_rm")):
    ss.clique_rm = clique                         # o mapa mantém o último clique; evita repetir
    i_rm = int(round((RM_LAT - clique["lat"]) / RM_PASSO))
    if 0 <= i_rm < len(refs):
        remover_area(refs[i_rm])
    st.rerun()

# [várias áreas] cada desenho novo vira mais uma área
if usa.get("draw"):
    drawing = (out or {}).get("last_active_drawing")
    if (drawing and drawing.get("geometry") and drawing not in [x["feat"] for x in ss.minhas_areas]
            and drawing not in ss.draw_ign):
        nova_area("draw", None, shape(drawing["geometry"]).wkt, feat=drawing)
        st.rerun()

# legenda (fora do mapa, para não cobrir nada)
cinza = f'<span class="legend-note"><span class="legend-swatch"></span>{T["fora_cob"]}</span>'
if tem_raster:
    st.markdown(f"""
<div class="legend">
  <span class="legend-title">{T["leg_titulo"]}</span>
  <span class="legend-scale"><span>{T["menor"]}</span>
    <span class="legend-bar" style="background: linear-gradient(90deg, {', '.join(PAL)});"></span>
    <span>{T["maior"]}</span></span>
  <span class="legend-note">{T["leg_nota"]} ({PAL_NOME})</span>
  {cinza}
</div>""", unsafe_allow_html=True)
elif poly_sel is None:
    st.markdown(f'<div class="legend"><span class="legend-note">{T["sel_hint"]}</span>{cinza}</div>',
                unsafe_allow_html=True)

poly = poly_sel if poly_sel is not None else (BR_SHAPE if BR_SHAPE is not None else box(-74, -34, -34, 6))

dentro_cel = shapely.contains_xy(poly, cells.lon.values, cells.lat.values)
for _, g in areas:                            # área menor que uma célula: usa a célula do centro dela
    if not shapely.contains_xy(g, cells.lon.values, cells.lat.values).any():
        c = g.centroid
        dentro_cel |= ((cells.gx == int(np.floor(c.x / RES))) & (cells.gy == int(np.floor(c.y / RES)))).values
inside = cells[dentro_cel]
if inside.empty:
    st.warning(T["sem_focos"])
    st.stop()

sel = h.merge(inside[["gx", "gy"]], on=["gx", "gy"])
mon_all = sel.groupby("month")[["modis", "viirs", "H"]].sum()
mon_all = mon_all.reindex(pd.date_range(DADOS_INI, ULT_MES, freq="MS"), fill_value=0)
mon = mon_all[(mon_all.index >= INI) & (mon_all.index <= FIM)]

cal = mon.H.groupby([mon.index.year, mon.index.month]).sum().unstack()
cal.columns = [MESES[i - 1] for i in cal.columns]
cal.index.name = T["ax_ano"]
med = cal.median()
anom = ((cal - med) / med.replace(0, np.nan) * 100).clip(-200, 200)

# janela parcial do mês atual (1..último dia com dados), por ano
with st.spinner(T["calculando"]):
    parc = janela_por_ano(inside[["gx", "gy"]].reset_index(drop=True), ULT.month, ULT.day)
parc = parc.reindex(range(ANO_BASE, ULT.year + 1), fill_value=0)
JANELA = f"1–{ULT.day} {MESES[ULT.month - 1]}"

# ---------------- indicadores (acima do mapa)
with kpi_box:
    v_atual = parc.get(ULT.year, 0)
    base = parc[parc.index < ULT.year]
    m_base = base.median() if len(base) else np.nan
    delta = (v_atual / m_base - 1) * 100 if m_base else np.nan

    # cor do selo pelo sinal: acima da mediana = vermelho claro; abaixo = verde claro
    if pd.notna(delta) and delta != 0:
        fg, bg = ("var(--danger)", "var(--danger_bg)") if delta > 0 else ("var(--success)", "var(--success_bg)")
        st.markdown(f"""<style>[data-testid="stMetricDelta"] {{ color: {fg} !important; background: {bg} !important; }}
                    [data-testid="stMetricDelta"] * {{ color: {fg} !important; }}</style>""",
                    unsafe_allow_html=True)

    k0, k1, k2, k3, k4 = st.columns(5)
    k0.metric(T["kpi_total"], f"{mon.H.sum():,.0f}", help=T["h_total"])
    if pd.notna(delta):
        seta = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        delta_txt = f"{seta} {delta:+.0f}% · {T['mediana'].lower()} {m_base:,.0f}"
    else:
        delta_txt = None
    k1.metric(f"{JANELA}/{ULT.year} {T['kpi_vs']}", f"{v_atual:,.0f} {T['focos']}",
              delta_txt, delta_color="off", help=T["h_vs"])
    k2.metric(T["kpi_ano"], int(cal.sum(axis=1).idxmax()), help=T["h_ano"])
    tp = temporada(med)                                                        # [temporada]
    k3.metric(T["kpi_temp"], f"{MESES[tp[0]]}–{MESES[tp[1]]} ({MESES[tp[2]]})" if tp else "—",
              help=T["temp_help"])
    k4.metric(T["kpi_cel"], len(inside), help=T["h_cel"])
    st.caption(T["unidade"] + " " + T["nota_parcial"].format(d=ULT.day, m=MESES[ULT.month - 1],
                                                               a0=ANO_BASE, a1=ULT.year - 1))

# ---------------- análises
st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(T["abas"])

with t1:
    fig = px.imshow(cal, color_continuous_scale=PAL, aspect="auto",
                    labels=dict(x=T["ax_mes"], y=T["ax_ano"], color=T["ax_focos"]))
    fig.update_traces(xgap=1, ygap=1)
    fig.update_traces(hovertemplate=f"{T['ax_mes']}: %{{x}}<br>{T['ax_ano']}: %{{y}}<br>"
                                    f"{T['ax_focos']}: %{{z:,.0f}}<extra></extra>")
    fig.update_yaxes(dtick=1)
    fig.update_layout(coloraxis_colorbar=dict(thickness=10, outlinewidth=0, len=0.9))
    st.plotly_chart(travar_zoom(estilo(fig, 540, grade=False), cal), use_container_width=True,
                    config=PLOT_CFG, theme=None)
    st.caption(T["cap_cal"])

with t2:
    ref = st.radio(T["ref_lbl"], ["med", "mean"], format_func=lambda k: T["ref_" + k],
                   horizontal=True, key="ref_anom")
    base_ref = cal.median() if ref == "med" else cal.mean()
    anom_ref = ((cal - base_ref) / base_ref.replace(0, np.nan) * 100).clip(-200, 200)
    lbl_pct = T["ax_pct"] if ref == "med" else T["ax_pct_mean"]
    fig = px.imshow(anom_ref, color_continuous_scale="RdBu_r", zmin=-200, zmax=200, aspect="auto",
                    labels=dict(x=T["ax_mes"], y=T["ax_ano"], color=lbl_pct))
    fig.update_traces(xgap=1, ygap=1)
    fig.update_traces(hovertemplate=f"{T['ax_mes']}: %{{x}}<br>{T['ax_ano']}: %{{y}}<br>"
                                    f"{lbl_pct}: %{{z:+.0f}}%<extra></extra>")
    fig.update_yaxes(dtick=1)
    fig.update_layout(coloraxis_colorbar=dict(thickness=10, outlinewidth=0, len=0.9))
    st.plotly_chart(travar_zoom(estilo(fig, 540, grade=False), anom_ref), use_container_width=True,
                    config=PLOT_CFG, theme=None)
    st.caption(T["cap_anom"] if ref == "med" else T["cap_anom_mean"])

with t3:
    cc1, cc2 = st.columns([1, 3])
    mes_sel = cc1.selectbox(T["mes_comp"], list(range(1, 13)), index=ULT.month - 1,
                            format_func=lambda i: MESES[i - 1])
    if mes_sel == ULT.month:                     # mês atual: janela parcial justa
        s, destaque, janela = parc, ULT.year, JANELA
    else:                                        # outros meses: mês completo
        s = mon_all.H[mon_all.index.month == mes_sel]
        s.index = s.index.year
        destaque = ULT.year if mes_sel < ULT.month else ULT.year - 1
        janela = MESES[mes_sel - 1]
    s = s[s.index >= ANO_BASE]
    v_dest = s.get(destaque, 0)
    m_comp = s[s.index < destaque].median()
    pos = int((s > v_dest).sum()) + 1

    cc2.markdown(f'<div class="comp-title">{T["titulo_comp"].format(j=janela)}</div>', unsafe_allow_html=True)
    cc2.caption(T["rank"].format(a=destaque, p=pos, n=len(s), j=janela))

    fig = go.Figure(go.Bar(x=s.index, y=s.values,
                           marker_color=[P["destaque"] if a == destaque else P["bar"] for a in s.index],
                           hovertemplate="%{x}: %{y:,.0f}<extra></extra>"))
    # [linhas] mediana e média com cores distintas (Okabe-Ito) e rótulos fora do gráfico, à direita
    m_media = s[s.index < destaque].mean()
    COR_MED, COR_MEDIA = "#D55E00", "#009E73"                    # Okabe-Ito: mediana / média
    fig.add_hline(y=m_comp, line_dash="dash", line_color=COR_MED, line_width=1.5)
    fig.add_hline(y=m_media, line_dash="dot", line_color=COR_MEDIA, line_width=2)
    med_acima = m_comp >= m_media
    for v_ref, nome, cor, sobe in [(m_comp, T["mediana"], COR_MED, med_acima),
                                   (m_media, T["media"], COR_MEDIA, not med_acima)]:
        fig.add_annotation(x=1, xref="paper", xanchor="left", xshift=8, y=v_ref, yref="y",
                           text=f"<b>{nome}</b><br>{v_ref:,.0f}", showarrow=False, align="left",
                           yshift=10 if sobe else -10, font=dict(color=cor, size=11))
    fig.update_xaxes(dtick=1, tickangle=-45, showgrid=False)
    fig.update_layout(showlegend=False, bargap=0.25)
    estilo(fig, 400)
    fig.update_layout(margin=dict(r=110))                         # espaço para os rótulos na lateral
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CFG, theme=None)
    st.caption(T["cap_comp"].format(a=destaque))

with t4:
    s = mon.rename(columns={"modis": T["s_modis"], "viirs": T["s_viirs"],
                            "H": T["s_harm"]}).reset_index(names=T["ax_mes"])
    fig = px.line(s.melt(T["ax_mes"], var_name=T["ax_serie"], value_name=T["ax_focos"]),
                  x=T["ax_mes"], y=T["ax_focos"], color=T["ax_serie"], line_dash=T["ax_serie"],
                  color_discrete_map=CORES)
    if INI <= pd.Timestamp(OV_START) <= FIM:
        fig.add_vline(x=OV_START, line_dash="dash", line_color=P["muted"])
    fig.update_traces(line_width=2)
    st.plotly_chart(estilo(fig, 420), use_container_width=True, config=PLOT_CFG, theme=None)
    st.caption(T["cap_serie"])

with t5:
    mape = lambda c: (abs(val.viirs - val[c]) / val.viirs).mean() * 100
    c1, c2, c3 = st.columns(3)
    c1.metric(T["s_modis"], f"{mape('modis'):.1f}%", help=T["h_val_modis"])
    c2.metric(T["m_kglob"], f"{mape('pred_global'):.1f}%", help=T["h_val_kglob"])
    c3.metric(T["m_khier"], f"{mape('pred_hier'):.1f}%", help=T["h_val_khier"])
    v = val.rename(columns={"viirs": T["s_real"], "pred_hier": T["s_prev"], "modis": T["s_modis"],
                            "month": T["ax_mes"]})[[T["ax_mes"], T["s_real"], T["s_prev"], T["s_modis"]]]
    fig = px.line(v.melt(T["ax_mes"], var_name=T["ax_serie"], value_name=T["ax_focos"]),
                  x=T["ax_mes"], y=T["ax_focos"], color=T["ax_serie"], line_dash=T["ax_serie"],
                  color_discrete_map=CORES)
    fig.update_traces(line_width=2)
    st.plotly_chart(estilo(fig, 400), use_container_width=True, config=PLOT_CFG, theme=None)
    st.caption(T["cap_val"])

with t6:
    c1, c2, c3 = st.columns(3)
    c1.download_button(T["dl_cal"], cal.round(0).to_csv().encode(), "calendario.csv",
                       use_container_width=True)
    c2.download_button(T["dl_serie"], mon.round(1).to_csv().encode(), "serie_mensal.csv",
                       use_container_width=True)
    if c3.button(T["dl_prep"], use_container_width=True):
        x0, y0, x1, y1 = poly.bounds
        # mesma regra da série harmonizada: MODIS antes de abr/2018, VIIRS depois (sem contar o mesmo fogo
        # duas vezes na sobreposição); harmonized_weight = 1 para VIIRS e k da célula para MODIS
        con = duckdb.connect()
        con.register("kt", kt)
        pts = con.execute(f"""
            SELECT p.latitude, p.longitude, p.date, p.frp, p.daynight, p.sensor,
                   CASE WHEN p.sensor = 'viirs' THEN 1.0 ELSE COALESCE(kt.k, {K_DOM}) END AS harmonized_weight
            FROM '{PTS}' p
            LEFT JOIN kt ON kt.gx = CAST(floor(p.longitude / {RES}) AS INT)
                        AND kt.gy = CAST(floor(p.latitude / {RES}) AS INT)
            WHERE p.longitude BETWEEN ? AND ? AND p.latitude BETWEEN ? AND ?
              AND p.date >= ? AND p.date < ?
              AND ((p.sensor = 'viirs' AND p.date >= '{OV_START}')
                OR (p.sensor = 'modis' AND p.date <  '{OV_START}'))
            ORDER BY p.date""",
            [x0, x1, y0, y1, INI.strftime("%Y-%m-%d"), FIM_EXCL.strftime("%Y-%m-%d")]).df()
        pts["harmonized_weight"] = pts.harmonized_weight.round(4)
        pts = pts[shapely.contains_xy(poly, pts.longitude.values, pts.latitude.values)]
        st.session_state.pts_csv = pts.to_csv(index=False).encode()
        st.session_state.pts_n = len(pts)
    if "pts_csv" in st.session_state:
        c3.download_button(f"{T['dl_focos']} ({st.session_state.pts_n:,} {T['linhas']})",
                           st.session_state.pts_csv, "focos.csv", use_container_width=True)
    st.caption(T["dl_hint"])
# ---------------- [tempo real] atualiza sozinho a cada `intervalo` minutos (só esta parte da página)
FIRMS_KEY = firms_key()
with t7:
    if not FIRMS_KEY:
        st.info(T["rt_sem_chave"], icon=":material/key:")
    else:
        st.fragment(run_every=intervalo * 60)(painel_tempo_real)(
            FIRMS_KEY, intervalo, tuple(alert_areas), poly_sel.wkt if poly_sel is not None else None,
            pais)

# ---------------- [alertas] últimos alertas e downloads
with t8:
    if not alertas_on:
        st.info(T["al_off"], icon=":material/notifications_off:")
    elif not FIRMS_KEY:
        st.warning(T["al_sem_chave"], icon=":material/key:")
    elif not alert_areas:
        st.warning(T["al_sem_area"], icon=":material/warning:")
    else:
        st.caption(T["al_status"].format(a=", ".join(n for n, _ in alert_areas), n=intervalo))

    hist = ss.hist
    if hist.empty:
        st.caption(T["al_vazio"])
    else:
        C = T["al_cols"]
        res = (hist.groupby("alerta_id")
                   .agg(**{C["quando"]: ("verificado_em", "first"), C["area"]: ("area", "first"),
                           C["focos"]: ("id", "size"), C["frp"]: ("frp", "max"),
                           C["ultima"]: ("data_hora_utc", "max")})
                   .sort_index(ascending=False).reset_index(drop=True))
        st.markdown(f'<div class="comp-title">{T["al_ultimos"]}</div>', unsafe_allow_html=True)
        st.dataframe(res.head(100), hide_index=True, use_container_width=True,
                     column_config={C["frp"]: st.column_config.NumberColumn(format="%.1f")})
        c1, c2, c3 = st.columns(3)
        c1.download_button(T["al_dl"], hist.to_csv(index=False).encode(), "alertas_focos.csv",
                           use_container_width=True)
        c2.download_button(T["al_dl_res"], res.to_csv(index=False).encode(), "alertas_resumo.csv",
                           use_container_width=True)
        with c3.popover(T["al_limpar"], use_container_width=True):
            st.caption(T["al_limpar_conf"])
            if st.button(T["al_limpar_ok"], type="primary", use_container_width=True):
                if os.path.exists(ALERT_FILE):
                    os.remove(ALERT_FILE)
                ss.hist = pd.DataFrame(columns=HIST_COLS)    # focos já vistos continuam marcados (sem re-alertar)
                st.rerun()