package com.rgpis.hde

import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt

enum class PriorityLevel(val label: String) {
    P1_CRITICAL("P1_CRITICAL"),
    P2_HIGH("P2_HIGH"),
    P3_MEDIUM("P3_MEDIUM"),
    P4_LOW("P4_LOW")
}

data class DefectIntelligence(
    val detection: RawDetection,
    val displayName: String,
    val priority: PriorityLevel,
    val anomalyScore: Int,
    val traceReductionPct: Int,
    val clearanceIntrusionPct: Int,
    val ipcViolation: Boolean,
    val currentDensityAm2: Double,
    val currentDensityStr: String,
    val crowdingFactor: Double,
    val signalIntegrityRisk: String,
    val thermalRisk: String,
    val physicalSignificance: String,
    val correctiveAction: String
)

data class BoardReport(
    val boardName: String,
    val inferenceMs: Long,
    val disposition: String,
    val dispositionReason: String,
    val totalDefects: Int,
    val p1Count: Int,
    val maxTraceLossPct: Int,
    val maxCurrentDensityStr: String,
    val maxAnomalyScore: Int,
    val defects: List<DefectIntelligence>
)

object EngineeringIntelligence {

    private const val BASE_J0 = 2.86e7 // IPC-2152 1A ref copper trace baseline (A/m^2)

    fun analyze(boardName: String, rawDefects: List<RawDetection>, inferenceMs: Long): BoardReport {
        val analyzed = rawDefects.map { det ->
            val areaNorm = (det.bboxNorm640.width() * det.bboxNorm640.height()) / (640f * 640f)
            val severityScale = (0.65f + min(1.0f, areaNorm * 120f) * 0.35f)

            when (det.className) {
                "short" -> {
                    val jVal = BASE_J0 * 4.5
                    DefectIntelligence(
                        detection = det,
                        displayName = "Copper Short / Bridge",
                        priority = PriorityLevel.P1_CRITICAL,
                        anomalyScore = (88 + det.confidence * 11).roundToInt().coerceAtMost(99),
                        traceReductionPct = 0,
                        clearanceIntrusionPct = 100,
                        ipcViolation = true,
                        currentDensityAm2 = jVal,
                        currentDensityStr = formatJ(jVal),
                        crowdingFactor = 4.5,
                        signalIntegrityRisk = "CRITICAL",
                        thermalRisk = "HIGH",
                        physicalSignificance = "Unintended copper bridge across adjacent nets violates IPC-A-600 minimum electrical clearance.",
                        correctiveAction = "Isolate under stereo microscope; perform controlled micro-abrasive bridge removal and verify >10 MOhm isolation."
                    )
                }
                "open" -> {
                    val jVal = BASE_J0 * 3.8
                    DefectIntelligence(
                        detection = det,
                        displayName = "Open Circuit / Trace Break",
                        priority = PriorityLevel.P1_CRITICAL,
                        anomalyScore = (90 + det.confidence * 9).roundToInt().coerceAtMost(99),
                        traceReductionPct = 100,
                        clearanceIntrusionPct = 0,
                        ipcViolation = true,
                        currentDensityAm2 = jVal,
                        currentDensityStr = formatJ(jVal),
                        crowdingFactor = 3.8,
                        signalIntegrityRisk = "CRITICAL",
                        thermalRisk = "MEDIUM",
                        physicalSignificance = "Complete copper discontinuity breaks DC continuity and causes total signal loss.",
                        correctiveAction = "Perform micro-jumper wire rework per IPC-7711/7721 or scrap panel if inner-layer."
                    )
                }
                "mousebite" -> {
                    val red = (28 + severityScale * 24).roundToInt().coerceIn(20, 65)
                    val mult = 1.0 / (1.0 - red / 100.0)
                    val jVal = BASE_J0 * mult
                    val isP1 = red >= 40
                    DefectIntelligence(
                        detection = det,
                        displayName = "Mousebite (Edge Notch)",
                        priority = if (isP1) PriorityLevel.P1_CRITICAL else PriorityLevel.P2_HIGH,
                        anomalyScore = (64 + red * 0.45).roundToInt().coerceAtMost(92),
                        traceReductionPct = red,
                        clearanceIntrusionPct = 0,
                        ipcViolation = red > 20,
                        currentDensityAm2 = jVal,
                        currentDensityStr = formatJ(jVal),
                        crowdingFactor = (mult * 100).roundToInt() / 100.0,
                        signalIntegrityRisk = "HIGH",
                        thermalRisk = if (red > 35) "HIGH" else "MEDIUM",
                        physicalSignificance = "Notched conductor edge narrows cross-sectional area, elevating impedance and localized Joule heating.",
                        correctiveAction = "Measure remaining trace width against IPC-A-600 Class 2/3 (>80% intact width required); reinforce or reject."
                    )
                }
                "spur" -> {
                    val intr = (25 + severityScale * 35).roundToInt().coerceIn(20, 75)
                    val jVal = BASE_J0 * 1.45
                    DefectIntelligence(
                        detection = det,
                        displayName = "Copper Spur / Protrusion",
                        priority = PriorityLevel.P2_HIGH,
                        anomalyScore = (58 + det.confidence * 22).roundToInt().coerceAtMost(84),
                        traceReductionPct = 0,
                        clearanceIntrusionPct = intr,
                        ipcViolation = intr > 30,
                        currentDensityAm2 = jVal,
                        currentDensityStr = formatJ(jVal),
                        crowdingFactor = 1.45,
                        signalIntegrityRisk = "MEDIUM",
                        thermalRisk = "LOW",
                        physicalSignificance = "Sharp copper protrusion reduces dielectric spacing and creates crosstalk/arcing risk.",
                        correctiveAction = "Trim copper spur mechanically under 20x magnification and inspect solder mask integrity."
                    )
                }
                "copper" -> {
                    val intr = (20 + severityScale * 30).roundToInt().coerceIn(15, 60)
                    val jVal = BASE_J0 * 1.25
                    DefectIntelligence(
                        detection = det,
                        displayName = "Spurious Copper Island",
                        priority = PriorityLevel.P3_MEDIUM,
                        anomalyScore = (44 + det.confidence * 24).roundToInt().coerceAtMost(72),
                        traceReductionPct = 0,
                        clearanceIntrusionPct = intr,
                        ipcViolation = intr > 40,
                        currentDensityAm2 = jVal,
                        currentDensityStr = formatJ(jVal),
                        crowdingFactor = 1.25,
                        signalIntegrityRisk = "MEDIUM",
                        thermalRisk = "LOW",
                        physicalSignificance = "Residual unetched copper island causes parasitic capacitance and violates minimum spacing.",
                        correctiveAction = "Remove spurious copper island and audit chemical etchant spray nozzle pressure."
                    )
                }
                else -> { // pin-hole
                    val red = (12 + severityScale * 18).roundToInt().coerceIn(10, 35)
                    val mult = 1.0 / (1.0 - red / 100.0)
                    val jVal = BASE_J0 * mult
                    DefectIntelligence(
                        detection = det,
                        displayName = "Copper Pin-Hole Void",
                        priority = PriorityLevel.P4_LOW,
                        anomalyScore = (30 + det.confidence * 22).roundToInt().coerceAtMost(58),
                        traceReductionPct = red,
                        clearanceIntrusionPct = 0,
                        ipcViolation = red > 20,
                        currentDensityAm2 = jVal,
                        currentDensityStr = formatJ(jVal),
                        crowdingFactor = (mult * 100).roundToInt() / 100.0,
                        signalIntegrityRisk = "LOW",
                        thermalRisk = "LOW",
                        physicalSignificance = "Localized void reduces copper cross-section slightly; monitor plating bath cleanliness.",
                        correctiveAction = "Verify conductor width meets IPC-A-600 Class 2/3 tolerance; log for plating/dry-film audit."
                    )
                }
            }
        }.sortedByDescending { it.anomalyScore }

        val p1Count = analyzed.count { it.priority == PriorityLevel.P1_CRITICAL }
        val p2Count = analyzed.count { it.priority == PriorityLevel.P2_HIGH }
        val maxTraceLoss = analyzed.maxOfOrNull { it.traceReductionPct } ?: 0
        val maxJ = analyzed.maxOfOrNull { it.currentDensityAm2 } ?: 0.0
        val maxScore = analyzed.maxOfOrNull { it.anomalyScore } ?: 0

        val (disposition, reason) = when {
            p1Count > 0 -> "REJECT" to "$p1Count P1 Critical defect(s) detected (Open/Short/Severe Trace Loss) violating IPC-A-600 Class 2/3."
            p2Count > 0 || analyzed.isNotEmpty() -> "REVIEW" to "${analyzed.size} non-critical anomaly(s) detected; engineering disposition required before release."
            else -> "ACCEPT" to "Zero optical PCB defects detected within IPC-A-600 Class 2/3 tolerances."
        }

        return BoardReport(
            boardName = boardName,
            inferenceMs = inferenceMs,
            disposition = disposition,
            dispositionReason = reason,
            totalDefects = analyzed.size,
            p1Count = p1Count,
            maxTraceLossPct = maxTraceLoss,
            maxCurrentDensityStr = if (maxJ == 0.0) "0.0 A·m⁻²" else formatJ(maxJ),
            maxAnomalyScore = maxScore,
            defects = analyzed
        )
    }

    private fun formatJ(j: Double): String {
        if (j <= 0.0) return "0.0 A·m⁻²"
        val exp = floor(log10(j)).toInt()
        val mant = j / 10.0.pow(exp)
        val supers = mapOf(
            '0' to '⁰', '1' to '¹', '2' to '²', '3' to '³', '4' to '⁴',
            '5' to '⁵', '6' to '⁶', '7' to '⁷', '8' to '⁸', '9' to '⁹', '-' to '⁻'
        )
        val expStr = exp.toString().map { supers[it] ?: it }.joinToString("")
        return String.format("%.2f × 10%s A·m⁻²", mant, expStr)
    }
}
