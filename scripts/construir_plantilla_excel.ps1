# Construye web/plantillas_excel/tablero_calidad.xlsx con Excel de escritorio.
#
# La plantilla trae la tabla "Consolidado" en el modelo de datos (Power
# Pivot), las medidas DAX y las tablas dinámicas del tablero. El panel web
# (web/exportar_excel.py) solo cambia las filas de la hoja "Datos"; todo
# lo demás sale de aquí. Solo hace falta volver a correrlo si cambian las
# columnas, las medidas o las tablas dinámicas.
#
# Uso (Windows con Excel 2016 o superior):
#   powershell -ExecutionPolicy Bypass -File scripts\construir_plantilla_excel.ps1

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$destino = Join-Path $raiz "web\plantillas_excel\tablero_calidad.xlsx"
New-Item -ItemType Directory -Force (Split-Path $destino) | Out-Null
if (Test-Path $destino) { Remove-Item $destino }

# Encabezados: deben coincidir con COLUMNAS en web/exportar_excel.py.
$columnas = @("Canal", "Periodo", "Fecha radicación", "Departamento", "Régimen", "Estado",
    "Clasificación", "Tipo de documento", "Efectiva", "Duplicado multicanal", "Duplicado interno",
    "No homologado", "Territorio incompleto", "Fecha inválida", "Registro crítico")
$muestra = @(
    @("Digital", "2026-01", 46027, "Antioquia", "CONTRIBUTIVO", "RADICADO", "Afiliación Nueva", "CC", 1, 0, 0, 0, 0, 0, 0),
    @("Físico", "2026-02", 46059, "Bogotá D.C.", "SUBSIDIADO", "RADICADO", "Traslado", "TI", 1, 1, 0, 0, 0, 0, 0),
    @("SAT", "2026-03", 46085, "Valle del Cauca", "CONTRIBUTIVO", "ANULADO", "Reinscripción", "CC", 0, 0, 1, 0, 1, 0, 1)
)

# Medidas DAX: (nombre, fórmula, formato "entero" o "porcentaje").
$medidas = @(
    @("Trámites", "COUNTROWS(Consolidado)", "entero"),
    @("Producción efectiva", "SUM(Consolidado[Efectiva])", "entero"),
    @("% Efectiva", "DIVIDE([Producción efectiva], [Trámites])", "porcentaje"),
    @("Duplicados multicanal", "SUM(Consolidado[Duplicado multicanal])", "entero"),
    @("% Duplicidad multicanal", "DIVIDE([Duplicados multicanal], [Trámites])", "porcentaje"),
    @("Duplicados internos", "SUM(Consolidado[Duplicado interno])", "entero"),
    @("% Duplicidad interna", "DIVIDE([Duplicados internos], [Trámites])", "porcentaje"),
    @("Registros críticos", "SUM(Consolidado[Registro crítico])", "entero"),
    @("% Críticos", "DIVIDE([Registros críticos], [Trámites])", "porcentaje"),
    @("% Homologación", "1 - DIVIDE(SUM(Consolidado[No homologado]), [Trámites])", "porcentaje"),
    @("% Territorio completo", "1 - DIVIDE(SUM(Consolidado[Territorio incompleto]), [Trámites])", "porcentaje")
)

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false
$xl.DisplayAlerts = $false
try {
    $wb = $xl.Workbooks.Add()
    while ($wb.Worksheets.Count -lt 3) { [void]$wb.Worksheets.Add([Type]::Missing, $wb.Worksheets.Item($wb.Worksheets.Count)) }
    $inicio = $wb.Worksheets.Item(1); $inicio.Name = "Inicio"
    $tablero = $wb.Worksheets.Item(2); $tablero.Name = "Tablero"
    $datos = $wb.Worksheets.Item(3); $datos.Name = "Datos"

    # ── Datos: tabla "Consolidado" ──
    # Una matriz bidimensional en una sola asignación: celda por celda, el
    # enlace COM de PowerShell falla al convertir números.
    $ultima = $muestra.Count + 1
    $matriz = New-Object 'object[,]' $ultima, $columnas.Count
    for ($c = 0; $c -lt $columnas.Count; $c++) { $matriz[0, $c] = $columnas[$c] }
    for ($f = 0; $f -lt $muestra.Count; $f++) {
        for ($c = 0; $c -lt $columnas.Count; $c++) { $matriz[($f + 1), $c] = $muestra[$f][$c] }
    }
    $datos.Range("A1:O$ultima").Value2 = $matriz
    $tabla = $datos.ListObjects.Add(1, $datos.Range("A1:O$ultima"), [Type]::Missing, 1)
    $tabla.Name = "Consolidado"
    $tabla.TableStyle = "TableStyleMedium3"
    $datos.Range("C2:C$ultima").NumberFormat = "dd/mm/yyyy"
    [void]$datos.Columns.Item("A:O").AutoFit()

    # Se guarda antes de crear la conexión: el modelo apunta al libro por su ruta.
    $wb.SaveAs($destino, 51)

    # ── Modelo de datos y medidas DAX ──
    # La tabla entra al modelo como tabla vinculada. Para que se recargue al
    # abrir, web/exportar_excel.py marca el libro con refreshAllConnections
    # (marcar la conexión del modelo deja el libro sin poder abrirse, y una
    # consulta de Power Query se traba al automatizarla desde aquí).
    [void]$wb.Connections.Add2("WorksheetConnection_Consolidado", "Tabla Consolidado del libro",
        "WORKSHEET;$destino", "$($wb.Name)!Consolidado", 7, $true, $false)
    $modelo = $wb.Model
    $tablaModelo = $modelo.ModelTables.Item("Consolidado")
    foreach ($m in $medidas) {
        $formato = if ($m[2] -eq "porcentaje") { $modelo.ModelFormatPercentageNumber($false, 1) } else { $modelo.ModelFormatWholeNumber($true) }
        [void]$modelo.ModelMeasures.Add($m[0], $tablaModelo, $m[1], $formato)
    }

    # ── Tablero: tablas dinámicas sobre el modelo ──
    $conexionModelo = $wb.Connections.Item("ThisWorkbookDataModel")
    function Nueva-Dinamica($celda, $nombre) {
        $cache = $wb.PivotCaches().Create(2, $conexionModelo, 6)
        $pt = $cache.CreatePivotTable($tablero.Range($celda), $nombre)
        $pt.TableStyle2 = "PivotStyleMedium3"
        $pt.RowAxisLayout(1)  # tabular: encabezados legibles
        return $pt
    }
    function Poner($pt, $campo, $orientacion) { $pt.CubeFields.Item($campo).Orientation = $orientacion }

    $tablero.Range("B2").Value2 = "Tablero de calidad de afiliaciones"
    $tablero.Range("B2").Font.Size = 18
    $tablero.Range("B2").Font.Bold = $true
    $tablero.Range("B3").Value2 = "Cada tabla dinámica usa las medidas DAX del modelo de datos. Filtra con las segmentaciones de la derecha."
    $tablero.Range("B3").Font.Color = 0x6B635A

    # Separadas en columnas para que ninguna se monte sobre otra al crecer.
    $resumen = Nueva-Dinamica "B7" "TD_Resumen"
    Poner $resumen "[Consolidado].[Canal]" 1
    foreach ($m in @("Trámites", "% Efectiva", "% Duplicidad multicanal", "% Duplicidad interna", "% Críticos", "% Homologación")) {
        Poner $resumen "[Measures].[$m]" 4
    }

    $periodo = Nueva-Dinamica "J7" "TD_Periodo"
    Poner $periodo "[Consolidado].[Periodo]" 1
    Poner $periodo "[Consolidado].[Canal]" 2
    Poner $periodo "[Measures].[Trámites]" 4

    $clasificacion = Nueva-Dinamica "Q7" "TD_Clasificacion"
    Poner $clasificacion "[Consolidado].[Clasificación]" 1
    Poner $clasificacion "[Measures].[Trámites]" 4
    Poner $clasificacion "[Measures].[% Efectiva]" 4

    $territorio = Nueva-Dinamica "U7" "TD_Territorio"
    Poner $territorio "[Consolidado].[Departamento]" 1
    Poner $territorio "[Measures].[Trámites]" 4
    Poner $territorio "[Measures].[% Territorio completo]" 4

    $tablero.Range("B6").Value2 = "Resumen por canal"
    $tablero.Range("J6").Value2 = "Trámites por periodo y canal"
    $tablero.Range("Q6").Value2 = "Clasificación del trámite"
    $tablero.Range("U6").Value2 = "Trámites por departamento"
    foreach ($c in @("B6", "J6", "Q6", "U6")) { $tablero.Range($c).Font.Bold = $true; $tablero.Range($c).Font.Size = 12 }

    # Segmentaciones conectadas a las cuatro tablas dinámicas.
    $izquierda = $tablero.Range("Y2").Left
    $fila = 0
    foreach ($campo in @("[Consolidado].[Canal]", "[Consolidado].[Régimen]")) {
        $sc = $wb.SlicerCaches.Add2($resumen, $campo)
        foreach ($pt in @($periodo, $clasificacion, $territorio)) { [void]$sc.PivotTables.AddPivotTable($pt) }
        $titulo = if ($campo -like "*Canal*") { "Canal" } else { "Régimen" }
        [void]$sc.Slicers.Add($tablero, [Type]::Missing, "Seg_$titulo", $titulo, 20 + $fila * 150, $izquierda, 160, 135)
        $fila++
    }
    $xl.ActiveWindow.DisplayGridlines = $false

    # ── Inicio: cómo usar el libro y qué calcula cada medida ──
    $inicio.Range("B2").Value2 = "Calidad de afiliaciones · libro con modelo de datos"
    $inicio.Range("B2").Font.Size = 18
    $inicio.Range("B2").Font.Bold = $true
    $pasos = @(
        "1. Si Excel abre en Vista protegida, pulsa 'Habilitar edición': el libro actualiza el modelo y las tablas dinámicas al abrirse.",
        "2. Si las tablas dinámicas siguen vacías, ve a Datos > Actualizar todo.",
        "3. La hoja 'Datos' tiene el consolidado de tu cuenta (una fila por afiliado). La hoja 'Tablero', las tablas dinámicas.",
        "4. Para tus propios análisis: Insertar > Tabla dinámica > 'Desde el modelo de datos' y arrastra las medidas de abajo.",
        "5. Las medidas se editan en Power Pivot > Administrar (o Datos > Herramientas de datos > Administrar modelo de datos)."
    )
    for ($i = 0; $i -lt $pasos.Count; $i++) { $inicio.Cells.Item(4 + $i, 2).Value2 = $pasos[$i] }
    $base = 4 + $pasos.Count + 2
    $inicio.Cells.Item($base, 2).Value2 = "Medida (DAX)"
    $inicio.Cells.Item($base, 3).Value2 = "Fórmula"
    $inicio.Range($inicio.Cells.Item($base, 2), $inicio.Cells.Item($base, 3)).Font.Bold = $true
    for ($i = 0; $i -lt $medidas.Count; $i++) {
        $inicio.Cells.Item($base + 1 + $i, 2).Value2 = $medidas[$i][0]
        $inicio.Cells.Item($base + 1 + $i, 3).Value2 = "'" + $medidas[$i][1]
    }
    $inicio.Columns.Item("B").ColumnWidth = 30
    $inicio.Columns.Item("C").ColumnWidth = 70
    $inicio.Activate()
    $xl.ActiveWindow.DisplayGridlines = $false

    $wb.Save()
    Write-Output "Plantilla creada: $destino"
} finally {
    if ($wb) { $wb.Close($false) }
    $xl.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
