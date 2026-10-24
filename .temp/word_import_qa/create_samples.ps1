$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Add-Type -AssemblyName System.IO.Compression
$targetDir = Join-Path $PSScriptRoot '../files'
$utf8 = [System.Text.UTF8Encoding]::new($false)
function XmlText([string]$value) { [System.Security.SecurityElement]::Escape($value) }
function Para([string]$value, [string]$style = 'Normal') {
    '<w:p><w:pPr><w:pStyle w:val="' + $style + '"/></w:pPr><w:r><w:t xml:space="preserve">' + (XmlText $value) + '</w:t></w:r></w:p>'
}
function TaskTable($rows) {
    $widths = @(1000, 2100, 2100, 2060, 2100)
    $borders = '<w:tblBorders>' + ((@('top','left','bottom','right','insideH','insideV') | ForEach-Object { '<w:' + $_ + ' w:val="single" w:sz="4" w:color="D9D9D9"/>' }) -join '') + '</w:tblBorders>'
    $table = '<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblLayout w:type="fixed"/>' + $borders + '<w:tblCellMar><w:top w:w="120" w:type="dxa"/><w:left w:w="140" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="140" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'
    foreach ($width in $widths) { $table += '<w:gridCol w:w="' + $width + '"/>' }
    $table += '</w:tblGrid>'
    for ($i = 0; $i -lt $rows.Count; $i++) {
        $table += '<w:tr><w:trPr><w:cantSplit/>'
        if ($i -eq 0) { $table += '<w:tblHeader/>' }
        $table += '</w:trPr>'
        for ($j = 0; $j -lt 5; $j++) {
            $table += '<w:tc><w:tcPr><w:tcW w:w="' + $widths[$j] + '" w:type="dxa"/><w:vAlign w:val="center"/>'
            if ($i -eq 0) { $table += '<w:shd w:fill="E8EEF4"/>' }
            $table += '</w:tcPr><w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="0" w:line="300" w:lineRule="auto"/></w:pPr><w:r><w:rPr>'
            if ($i -eq 0) { $table += '<w:b/>' }
            $table += '</w:rPr><w:t>' + (XmlText $rows[$i][$j]) + '</w:t></w:r></w:p></w:tc>'
        }
        $table += '</w:tr>'
    }
    $table + '</w:tbl>'
}
function SaveDocx([string]$filename, [string]$body) {
    $parts = @{
        '[Content_Types].xml' = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'
        '_rels/.rels' = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
        'word/_rels/document.xml.rels' = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
        'word/styles.xml' = '<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/><w:color w:val="000000"/><w:sz w:val="22"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="340" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:after="280"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="36"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="26"/></w:rPr></w:style></w:styles>'
        'word/document.xml' = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + $body + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1273" w:bottom="1134" w:left="1273" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr></w:body></w:document>'
    }
    $filePath = Join-Path $targetDir $filename
    $stream = [System.IO.File]::Open($filePath, [System.IO.FileMode]::Create)
    $archive = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($part in $parts.GetEnumerator()) {
            [xml]$check = $part.Value
            $entry = $archive.CreateEntry($part.Key)
            $writer = [System.IO.StreamWriter]::new($entry.Open(), $utf8)
            try { $writer.Write($part.Value) } finally { $writer.Dispose() }
        }
    } finally { $archive.Dispose(); $stream.Dispose() }
    Write-Output $filename
}

$body = (Para '仓库搬运交接单' 'Title') + (Para '本交接单列出本次待执行的三项搬运需求，请逐项核对取送地点与优先级。')
$body += (Para '普通订单' 'Heading1') + (Para '订单W01：从1号货架取货，送往1号配送点，搬运1次，优先级2级。')
$body += (Para '紧急订单' 'Heading1') + (Para '订单W02：从2号货架取货，送往2号配送点，搬运1次，紧急，优先级5级。')
$body += (Para '补货订单' 'Heading1') + (Para '订单W03：从取货点03（P03）向1号配送点（D1）搬运1次，优先级3级。')
SaveDocx '09_Word正文交接单.docx' $body

$body = (Para '仓库搬运任务表' 'Title') + (Para '下表三项均为待执行订单。搬运次数表示独立任务次数，取送地点使用地图正式ID。')
$rows = @(@('订单','取货点','配送点','搬运次数','优先级'), @('W11','P01','D1','1次','2级'), @('W12','P02','D2','2次','5级'), @('W13','P03','D1','1次','3级'))
$body += TaskTable $rows
SaveDocx '10_Word表格搬运清单.docx' $body

$body = (Para '搬运需求数量核对单' 'Title') + (Para '以下四项均待执行。部分订单仅提供货物数量或模糊次数，需要在创建前补充搬运次数。')
$body += (Para '订单W21：从P01向D1搬运3次，优先级2级。')
$body += (Para '订单W22：将P02的12箱零件送到D2，优先级2级。每次可搬运多少箱尚未确认。')
$body += (Para '订单W23：从P03取货送往D1，优先级2级。')
$body += (Para '订单W24：从P04向D2搬运几趟，优先级2级，具体趟数待确认。')
SaveDocx '11_Word数量歧义.docx' $body

$body = (Para '待补充搬运需求单' 'Title') + (Para '本单包含三项待执行需求及一条历史记录。待执行需求中的地点缺失和特殊运输条件需要核对。')
$body += (Para '本次待执行' 'Heading1')
$body += (Para '订单W31：从未在当前地图登记的月球仓库Z99取货，送往D1，搬运1次，优先级2级。')
$body += (Para '订单W32：从P02取货，搬运1次，优先级2级。配送点待人工确定。')
$body += (Para '订单W33：从P03向D2搬运1次，优先级2级。必须指定机器人R01执行，在2026年10月23日09:00前完成，并全程保持冷链。')
$body += (Para '历史记录' 'Heading1') + (Para '昨天从P04到D1的1次搬运已经完成，仅保留记录，本次不执行。')
SaveDocx '12_Word信息缺失与约束.docx' $body

$body = (Para '待审核搬运订单' 'Title') + (Para '本单尚有未处理的修订，需审核后才能确定最终搬运要求。')
$body += '<w:p><w:r><w:t>订单W41：从P01向D1搬运</w:t></w:r><w:del w:id="1" w:author="AWCS Test" w:date="2026-10-22T06:00:00Z"><w:r><w:delText>1次</w:delText></w:r></w:del><w:ins w:id="2" w:author="AWCS Test" w:date="2026-10-22T06:00:00Z"><w:r><w:t>2次</w:t></w:r></w:ins><w:r><w:t>，优先级2级。</w:t></w:r></w:p>'
SaveDocx '13_Word含未处理修订_应拒绝.docx' $body
