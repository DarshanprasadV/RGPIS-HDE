package com.rgpis.hde

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.RectF
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer
import kotlin.math.max
import kotlin.math.min

data class RawDetection(
    val id: Int,
    val classId: Int,
    val className: String,
    val confidence: Float,
    val bboxOrig: RectF,       // x1, y1, x2, y2 in original bitmap pixels
    val bboxNorm640: RectF     // x1, y1, x2, y2 normalized to 640x640
)

class YoloOnnxDetector(context: Context) : AutoCloseable {

    companion object {
        private const val MODEL_ASSET = "best.onnx"
        private const val INPUT_SIZE = 640
        private const val NUM_CLASSES = 6
        private const val NUM_ANCHORS = 8400
        private const val CONF_THRESHOLD = 0.25f
        private const val IOU_THRESHOLD = 0.45f

        val CLASS_NAMES = arrayOf(
            "open",
            "short",
            "mousebite",
            "spur",
            "copper",
            "pin-hole"
        )
    }

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession

    init {
        val modelBytes = context.assets.open(MODEL_ASSET).use { it.readBytes() }
        val opts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(4)
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        session = env.createSession(modelBytes, opts)
    }

    fun detect(bitmap: Bitmap): List<RawDetection> {
        val origW = bitmap.width
        val origH = bitmap.height

        // Letterbox to 640x640 preserving aspect ratio
        val scale = min(INPUT_SIZE.toFloat() / origW, INPUT_SIZE.toFloat() / origH)
        val newW = (origW * scale).toInt().coerceAtLeast(1)
        val newH = (origH * scale).toInt().coerceAtLeast(1)
        val padX = (INPUT_SIZE - newW) / 2f
        val padY = (INPUT_SIZE - newH) / 2f

        val letterboxed = Bitmap.createBitmap(INPUT_SIZE, INPUT_SIZE, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(letterboxed)
        canvas.drawColor(Color.rgb(114, 114, 114))
        val scaled = Bitmap.createScaledBitmap(bitmap, newW, newH, true)
        canvas.drawBitmap(scaled, padX, padY, null)
        if (scaled !== bitmap) scaled.recycle()

        // Convert RGB pixels to NCHW float buffer [1, 3, 640, 640] normalized to [0, 1]
        val pixels = IntArray(INPUT_SIZE * INPUT_SIZE)
        letterboxed.getPixels(pixels, 0, INPUT_SIZE, 0, 0, INPUT_SIZE, INPUT_SIZE)
        letterboxed.recycle()

        val planeSize = INPUT_SIZE * INPUT_SIZE
        val floatArray = FloatArray(3 * planeSize)
        for (i in 0 until planeSize) {
            val px = pixels[i]
            floatArray[i] = ((px shr 16) and 0xFF) / 255f
            floatArray[planeSize + i] = ((px shr 8) and 0xFF) / 255f
            floatArray[2 * planeSize + i] = (px and 0xFF) / 255f
        }

        val inputName = session.inputNames.first()
        val shape = longArrayOf(1, 3, INPUT_SIZE.toLong(), INPUT_SIZE.toLong())
        val candidates = mutableListOf<RawDetection>()

        OnnxTensor.createTensor(env, FloatBuffer.wrap(floatArray), shape).use { tensor ->
            session.run(mapOf(inputName to tensor)).use { results ->
                @Suppress("UNCHECKED_CAST")
                val rawOut = (results[0].value as Array<Array<FloatArray>>)[0] // [10, 8400]

                for (a in 0 until NUM_ANCHORS) {
                    var bestClass = -1
                    var bestConf = 0f
                    for (c in 0 until NUM_CLASSES) {
                        val score = rawOut[4 + c][a]
                        if (score > bestConf) {
                            bestConf = score
                            bestClass = c
                        }
                    }

                    if (bestConf < CONF_THRESHOLD || bestClass < 0) continue

                    val cx = rawOut[0][a]
                    val cy = rawOut[1][a]
                    val w = rawOut[2][a]
                    val h = rawOut[3][a]

                    val x1_640 = cx - w / 2f
                    val y1_640 = cy - h / 2f
                    val x2_640 = cx + w / 2f
                    val y2_640 = cy + h / 2f

                    // Map back from letterboxed 640x640 to original image coordinates
                    val ox1 = ((x1_640 - padX) / scale).coerceIn(0f, origW.toFloat())
                    val oy1 = ((y1_640 - padY) / scale).coerceIn(0f, origH.toFloat())
                    val ox2 = ((x2_640 - padX) / scale).coerceIn(0f, origW.toFloat())
                    val oy2 = ((y2_640 - padY) / scale).coerceIn(0f, origH.toFloat())

                    if (ox2 <= ox1 || oy2 <= oy1) continue

                    candidates.add(
                        RawDetection(
                            id = 0,
                            classId = bestClass,
                            className = CLASS_NAMES[bestClass],
                            confidence = bestConf,
                            bboxOrig = RectF(ox1, oy1, ox2, oy2),
                            bboxNorm640 = RectF(
                                (ox1 / origW) * INPUT_SIZE,
                                (oy1 / origH) * INPUT_SIZE,
                                (ox2 / origW) * INPUT_SIZE,
                                (oy2 / origH) * INPUT_SIZE
                            )
                        )
                    )
                }
            }
        }

        // Per-class NMS
        val kept = nonMaxSuppression(candidates)
        return kept.mapIndexed { idx, det -> det.copy(id = idx + 1) }
    }

    private fun nonMaxSuppression(boxes: List<RawDetection>): List<RawDetection> {
        val sorted = boxes.sortedByDescending { it.confidence }.toMutableList()
        val result = mutableListOf<RawDetection>()

        while (sorted.isNotEmpty()) {
            val best = sorted.removeAt(0)
            result.add(best)
            val iter = sorted.iterator()
            while (iter.hasNext()) {
                val other = iter.next()
                if (other.classId == best.classId && iou(best.bboxOrig, other.bboxOrig) > IOU_THRESHOLD) {
                    iter.remove()
                }
            }
        }
        return result
    }

    private fun iou(a: RectF, b: RectF): Float {
        val ix1 = max(a.left, b.left)
        val iy1 = max(a.top, b.top)
        val ix2 = min(a.right, b.right)
        val iy2 = min(a.bottom, b.bottom)
        val inter = max(0f, ix2 - ix1) * max(0f, iy2 - iy1)
        val areaA = max(0f, a.width()) * max(0f, a.height())
        val areaB = max(0f, b.width()) * max(0f, b.height())
        val union = areaA + areaB - inter
        return if (union > 0f) inter / union else 0f
    }

    override fun close() {
        session.close()
        env.close()
    }
}
