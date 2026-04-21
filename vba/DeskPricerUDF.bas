Attribute VB_Name = "DeskPricerUDF"
' DeskPricer non-volatile Excel UDFs
' Import via VBA Editor: File -> Import File -> DeskPricerUDF.bas
'
' These UDFs are NON-VOLATILE: they only recalculate when their arguments change.
' This avoids the constant re-calculation problem of Excel's built-in WEBSERVICE.
'
' Usage example:
'   =DeskGreek(C2, K2, T2, R2, Q2, V2, TYPE2, STYLE2, "price")
'   =DeskGreek(C2, K2, T2, R2, Q2, V2, TYPE2, STYLE2, "delta")
'   =DeskGreek(C2, K2, T2, R2, Q2, V2, TYPE2, STYLE2, "gamma")
'   =DeskGreek(C2, K2, T2, R2, Q2, V2, TYPE2, STYLE2, "vega")
'   =DeskGreek(C2, K2, T2, R2, Q2, V2, TYPE2, STYLE2, "theta")
'   =DeskGreek(C2, K2, T2, R2, Q2, V2, TYPE2, STYLE2, "rho")
'   =DeskGreek(C2, K2, T2, R2, Q2, V2, TYPE2, STYLE2, "charm")
'
' For implied volatility (back out IV from market price):
'   =DeskIV(C2, K2, T2, R2, Q2, P2, TYPE2, STYLE2)

Option Explicit

' Default host. Change if your service runs on a different port.
Private Const DEFAULT_HOST As String = "127.0.0.1:8765"

' ---------------------------------------------------------------------------
' Core helper: synchronous HTTP GET with XML XPath extraction
' ---------------------------------------------------------------------------
Private Function HttpGetXml(ByVal url As String, ByVal xpath As String) As Variant
    On Error GoTo ErrHandler
    
    Dim http As Object
    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", url, False
    http.setRequestHeader "Accept", "application/xml"
    http.send
    
    If http.Status <> 200 Then
        HttpGetXml = CVErr(xlErrValue)
        Exit Function
    End If
    
    Dim xmlDoc As Object
    Set xmlDoc = CreateObject("MSXML2.DOMDocument")
    xmlDoc.async = False
    xmlDoc.loadXML http.responseText
    
    If xmlDoc.parseError.errorCode <> 0 Then
        HttpGetXml = CVErr(xlErrValue)
        Exit Function
    End If
    
    xmlDoc.setProperty "SelectionLanguage", "XPath"
    
    Dim node As Object
    Set node = xmlDoc.selectSingleNode(xpath)
    If node Is Nothing Then
        HttpGetXml = CVErr(xlErrNA)
        Exit Function
    End If
    
    HttpGetXml = CDbl(node.Text)
    Exit Function
    
ErrHandler:
    HttpGetXml = CVErr(xlErrValue)
End Function

' ---------------------------------------------------------------------------
' Greeks UDF  (non-volatile)
' ---------------------------------------------------------------------------
Function DeskGreek(ByVal s As Variant, ByVal k As Variant, ByVal t As Variant, _
                   ByVal r As Variant, ByVal q As Variant, ByVal v As Variant, _
                   ByVal optType As Variant, ByVal style As Variant, _
                   ByVal field As Variant, _
                   Optional ByVal steps As Variant = 400, _
                   Optional ByVal host As Variant = DEFAULT_HOST) As Variant
    
    On Error GoTo ErrHandler
    
    Dim url As String
    url = "http://" & host & "/v1/greeks" & _
          "?s=" & CStr(s) & _
          "&k=" & CStr(k) & _
          "&t=" & CStr(t) & _
          "&r=" & CStr(r) & _
          "&q=" & CStr(q) & _
          "&v=" & CStr(v) & _
          "&type=" & LCase(CStr(optType)) & _
          "&style=" & LCase(CStr(style)) & _
          "&steps=" & CStr(steps)
    
    DeskGreek = HttpGetXml(url, "//outputs/" & LCase(CStr(field)))
    Exit Function
    
ErrHandler:
    DeskGreek = CVErr(xlErrValue)
End Function

' ---------------------------------------------------------------------------
' Implied Volatility UDF  (non-volatile)
' ---------------------------------------------------------------------------
Function DeskIV(ByVal s As Variant, ByVal k As Variant, ByVal t As Variant, _
                ByVal r As Variant, ByVal q As Variant, ByVal marketPrice As Variant, _
                ByVal optType As Variant, ByVal style As Variant, _
                Optional ByVal steps As Variant = 400, _
                Optional ByVal host As Variant = DEFAULT_HOST) As Variant
    
    On Error GoTo ErrHandler
    
    Dim url As String
    url = "http://" & host & "/v1/impliedvol" & _
          "?s=" & CStr(s) & _
          "&k=" & CStr(k) & _
          "&t=" & CStr(t) & _
          "&r=" & CStr(r) & _
          "&q=" & CStr(q) & _
          "&price=" & CStr(marketPrice) & _
          "&type=" & LCase(CStr(optType)) & _
          "&style=" & LCase(CStr(style)) & _
          "&steps=" & CStr(steps)
    
    DeskIV = HttpGetXml(url, "//outputs/implied_vol")
    Exit Function
    
ErrHandler:
    DeskIV = CVErr(xlErrValue)
End Function

' ---------------------------------------------------------------------------
' Health check UDF  (non-volatile)
' ---------------------------------------------------------------------------
Function DeskPricerStatus(Optional ByVal host As Variant = DEFAULT_HOST) As Variant
    On Error GoTo ErrHandler
    
    Dim url As String
    url = "http://" & host & "/v1/health"
    
    Dim http As Object
    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", url, False
    http.send
    
    If http.Status <> 200 Then
        DeskPricerStatus = "DOWN"
        Exit Function
    End If
    
    Dim xmlDoc As Object
    Set xmlDoc = CreateObject("MSXML2.DOMDocument")
    xmlDoc.async = False
    xmlDoc.loadXML http.responseText
    
    Dim node As Object
    Set node = xmlDoc.selectSingleNode("//status")
    If node Is Nothing Then
        DeskPricerStatus = "DOWN"
    Else
        DeskPricerStatus = node.Text
    End If
    Exit Function
    
ErrHandler:
    DeskPricerStatus = "DOWN"
End Function
