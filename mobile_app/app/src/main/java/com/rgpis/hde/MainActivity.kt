package com.rgpis.hde

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Memory
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

private val BgDark = Color(0xFF050811)
private val CardBg = Color(0xFF0D1323)
private val CardBorder = Color(0xFF1F2D4D)
private val AccentBlue = Color(0xFF3B82F6)
private val AccentIndigo = Color(0xFF6366F1)
private val DangerRed = Color(0xFFEF4444)
private val WarningAmber = Color(0xFFF59E0B)
private val SuccessGreen = Color(0xFF10B981)
private val TextMain = Color(0xFFF0F4FF)
private val TextMuted = Color(0xFF8B9BB8)

class MainActivity : ComponentActivity() {
    private var detector: YoloOnnxDetector? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(background = BgDark, surface = CardBg)) {
                Surface(modifier = Modifier.fillMaxSize(), color = BgDark) {
                    RGPISMobileApp(
                        getDetector = {
                            if (detector == null) detector = YoloOnnxDetector(applicationContext)
                            detector!!
                        }
                    )
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        detector?.close()
    }
}

@Composable
fun RGPISMobileApp(getDetector: () -> YoloOnnxDetector) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var currentBitmap by remember { mutableStateOf<Bitmap?>(null) }
    var report by remember { mutableStateOf<BoardReport?>(null) }
    var isAnalyzing by remember { mutableStateOf(false) }
    var statusMsg by remember { mutableStateOf("Offline ONNX Engine Ready (best.onnx)") }
    var cameraUri by remember { mutableStateOf<Uri?>(null) }

    fun runInspection(bmp: Bitmap, label: String) {
        currentBitmap = bmp
        isAnalyzing = true
        statusMsg = "Running offline YOLO26n inference on $label..."
        scope.launch {
            val result = withContext(Dispatchers.Default) {
                val t0 = System.currentTimeMillis()
                val det = getDetector()
                val raw = det.detect(bmp)
                val elapsed = System.currentTimeMillis() - t0
                EngineeringIntelligence.analyze(label, raw, elapsed)
            }
            report = result
            isAnalyzing = false
            statusMsg = "Analyzed $label in ${result.inferenceMs} ms · ${result.totalDefects} defect(s)"
        }
    }

    // Load bundled sample board on first launch
    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            runCatching {
                context.assets.open("sample_pcb.jpg").use { BitmapFactory.decodeStream(it) }
            }.getOrNull()
        }?.let { sampleBmp ->
            runInspection(sampleBmp, "deep_12100046 (Sample)")
        }
    }

    val galleryLauncher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri ?: return@rememberLauncherForActivityResult
        scope.launch {
            val bmp = withContext(Dispatchers.IO) {
                context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it) }
            }
            if (bmp != null) runInspection(bmp, "Gallery Capture")
        }
    }

    val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok && cameraUri != null) {
            scope.launch {
                val bmp = withContext(Dispatchers.IO) {
                    context.contentResolver.openInputStream(cameraUri!!)?.use { BitmapFactory.decodeStream(it) }
                }
                if (bmp != null) runInspection(bmp, "Camera Capture")
            }
        }
    }

    fun launchCamera() {
        val file = File(context.cacheDir, "pcb_${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        cameraUri = uri
        cameraLauncher.launch(uri)
    }

    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) launchCamera() else statusMsg = "Camera permission denied"
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(BgDark)
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        contentPadding = PaddingValues(top = 18.dp, bottom = 28.dp)
    ) {
        // Header Card
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = CardBg),
                border = BorderStroke(1.dp, CardBorder),
                shape = RoundedCornerShape(16.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                "RGPIS-HDE Mobile",
                                color = TextMain,
                                fontSize = 20.sp,
                                fontWeight = FontWeight.ExtraBold
                            )
                            Text(
                                "Offline Edge PCB Inspector · IPC-A-600",
                                color = TextMuted,
                                fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace
                            )
                        }
                        DispositionPill(report?.disposition ?: "READY")
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(if (isAnalyzing) WarningAmber else SuccessGreen)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(statusMsg, color = TextMuted, fontSize = 11.5.sp)
                    }
                }
            }
        }

        // Action Buttons (Camera / Gallery / Sample)
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Button(
                    onClick = {
                        val granted = ContextCompat.checkSelfPermission(
                            context, Manifest.permission.CAMERA
                        ) == PackageManager.PERMISSION_GRANTED
                        if (granted) launchCamera() else permissionLauncher.launch(Manifest.permission.CAMERA)
                    },
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = AccentBlue)
                ) {
                    Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Scan PCB", fontWeight = FontWeight.Bold)
                }

                OutlinedButton(
                    onClick = { galleryLauncher.launch("image/*") },
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    border = BorderStroke(1.dp, AccentIndigo),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = TextMain)
                ) {
                    Icon(Icons.Default.PhotoLibrary, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Gallery", fontWeight = FontWeight.Bold)
                }

                OutlinedButton(
                    onClick = {
                        scope.launch {
                            val bmp = withContext(Dispatchers.IO) {
                                context.assets.open("sample_pcb.jpg").use { BitmapFactory.decodeStream(it) }
                            }
                            if (bmp != null) runInspection(bmp, "deep_12100046")
                        }
                    },
                    modifier = Modifier.height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    border = BorderStroke(1.dp, CardBorder),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = TextMuted)
                ) {
                    Icon(Icons.Default.Memory, contentDescription = "Sample", modifier = Modifier.size(18.dp))
                }
            }
        }

        // KPI Grid
        report?.let { rep ->
            item {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        KpiCard("Defects", "${rep.totalDefects}", "YOLO26n 640px", AccentBlue, Modifier.weight(1f))
                        KpiCard("P1 Critical", "${rep.p1Count}", "IPC Reject", DangerRed, Modifier.weight(1f))
                        KpiCard("Anomaly", "${rep.maxAnomalyScore}/100", "Peak Severity", AccentIndigo, Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        KpiCard("Max Trace Loss", "${rep.maxTraceLossPct}%", "CERI Optical", WarningAmber, Modifier.weight(1f))
                        KpiCard("Current Density", rep.maxCurrentDensityStr, "CEIA Proxy (1A)", Color(0xFFA855F7), Modifier.weight(1.3f))
                    }
                }
            }
        }

        // Interactive PCB Defect Map
        currentBitmap?.let { bmp ->
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = CardBg),
                    border = BorderStroke(1.dp, CardBorder),
                    shape = RoundedCornerShape(16.dp)
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Text(
                            "Board Defect Map (On-Device)",
                            color = TextMain,
                            fontWeight = FontWeight.Bold,
                            fontSize = 14.sp
                        )
                        Spacer(Modifier.height(10.dp))
                        val aspect = bmp.width.toFloat() / bmp.height.coerceAtLeast(1)
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .aspectRatio(aspect)
                                .clip(RoundedCornerShape(10.dp))
                                .border(1.dp, AccentBlue.copy(alpha = 0.35f), RoundedCornerShape(10.dp))
                        ) {
                            Image(
                                bitmap = bmp.asImageBitmap(),
                                contentDescription = "Inspected PCB",
                                contentScale = ContentScale.FillBounds,
                                modifier = Modifier.fillMaxSize()
                            )
                            val defects = report?.defects.orEmpty()
                            Canvas(modifier = Modifier.fillMaxSize()) {
                                val sx = size.width / bmp.width
                                val sy = size.height / bmp.height
                                defects.forEach { item ->
                                    val r = item.detection.bboxOrig
                                    val col = priorityColor(item.priority)
                                    drawRect(
                                        color = col,
                                        topLeft = Offset(r.left * sx, r.top * sy),
                                        size = Size(r.width() * sx, r.height() * sy),
                                        style = Stroke(width = 5f)
                                    )
                                }
                            }
                            if (isAnalyzing) {
                                Box(
                                    modifier = Modifier
                                        .fillMaxSize()
                                        .background(Color.Black.copy(alpha = 0.55f)),
                                    contentAlignment = Alignment.Center
                                ) {
                                    CircularProgressIndicator(color = AccentBlue)
                                }
                            }
                        }
                        Spacer(Modifier.height(8.dp))
                        Text(
                            report?.dispositionReason ?: "",
                            color = TextMuted,
                            fontSize = 12.sp
                        )
                    }
                }
            }
        }

        // Defect Intelligence Cards
        val defectList = report?.defects.orEmpty()
        if (defectList.isNotEmpty()) {
            item {
                Text(
                    "Detected Defect Intelligence (${defectList.size})",
                    color = TextMain,
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp
                )
            }
            items(defectList, key = { it.detection.id }) { item ->
                DefectCard(item)
            }
        }
    }
}

@Composable
fun DispositionPill(disposition: String) {
    val bg = when (disposition) {
        "REJECT" -> DangerRed
        "REVIEW" -> WarningAmber
        "ACCEPT" -> SuccessGreen
        else -> AccentBlue
    }
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(10.dp))
            .background(bg)
            .padding(horizontal = 14.dp, vertical = 7.dp)
    ) {
        Text(disposition, color = Color.White, fontWeight = FontWeight.Black, fontSize = 13.sp, letterSpacing = 1.sp)
    }
}

@Composable
fun KpiCard(label: String, value: String, sub: String, accent: Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = CardBg),
        border = BorderStroke(1.dp, accent.copy(alpha = 0.35f)),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier
                .background(Brush.verticalGradient(listOf(accent.copy(alpha = 0.12f), Color.Transparent)))
                .padding(12.dp)
        ) {
            Text(label.uppercase(), color = TextMuted, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Text(value, color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
            Text(sub, color = TextMuted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
fun DefectCard(item: DefectIntelligence) {
    var expanded by remember { mutableStateOf(false) }
    val pColor = priorityColor(item.priority)

    Card(
        colors = CardDefaults.cardColors(containerColor = CardBg),
        border = BorderStroke(1.dp, pColor.copy(alpha = 0.45f)),
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded }
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "#${item.detection.id} ${item.displayName}",
                        color = TextMain,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
                    Text(
                        "${item.priority.label} · Score ${item.anomalyScore}/100 · Conf ${(item.detection.confidence * 100).toInt()}%",
                        color = pColor,
                        fontSize = 11.5.sp,
                        fontFamily = FontFamily.Monospace
                    )
                }
                Icon(
                    if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = null,
                    tint = TextMuted
                )
            }

            AnimatedVisibility(visible = expanded) {
                Column(modifier = Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    HorizontalDivider(color = CardBorder)
                    Text("Physical Significance", color = TextMuted, fontSize = 10.5.sp, fontWeight = FontWeight.Bold)
                    Text(item.physicalSignificance, color = TextMain, fontSize = 12.5.sp)

                    Text("CERI & CEIA Metrics", color = TextMuted, fontSize = 10.5.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "• Trace Reduction: ${item.traceReductionPct}%  |  Clearance Intrusion: ${item.clearanceIntrusionPct}%\n" +
                            "• Current Density J: ${item.currentDensityStr} (${item.crowdingFactor}x)\n" +
                            "• SI Risk: ${item.signalIntegrityRisk}  |  Thermal: ${item.thermalRisk}",
                        color = Color(0xFFCBD5E1),
                        fontSize = 12.sp
                    )

                    Text("IPC-A-600 Corrective Action", color = AccentBlue, fontSize = 10.5.sp, fontWeight = FontWeight.Bold)
                    Text(item.correctiveAction, color = TextMain, fontSize = 12.5.sp)
                }
            }
        }
    }
}

fun priorityColor(p: PriorityLevel): Color = when (p) {
    PriorityLevel.P1_CRITICAL -> DangerRed
    PriorityLevel.P2_HIGH -> Color(0xFFF97316)
    PriorityLevel.P3_MEDIUM -> Color(0xFFEAB308)
    PriorityLevel.P4_LOW -> Color(0xFF06B6D4)
}
