package org.smartlock.course;

import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.zip.CRC32;

/** Wire-compatible with smartlock_protocol.audio. CRC is not authentication. */
public final class OfdmCodec {
    public static final int FFT = 256, PREFIX = 64, SYMBOL = 320, MAX_PAYLOAD = 2048;
    private static final int CARRIERS = 64, FIRST_BIN = 16;
    // NumPy default_rng(3101).choice((-1.0, 1.0), (2,64)); fixed wire-format constant.
    static final int[][] TRAINING = {
        {-1,1,1,-1,-1,-1,1,-1,1,-1,1,1,-1,-1,1,1,-1,1,-1,1,-1,-1,-1,1,-1,-1,1,-1,-1,-1,1,1,1,-1,1,1,-1,1,-1,-1,-1,-1,1,-1,-1,1,-1,-1,1,1,1,-1,1,1,1,-1,1,1,-1,-1,1,-1,-1,1},
        {-1,-1,-1,1,1,-1,-1,-1,1,-1,1,1,-1,-1,-1,-1,-1,1,1,1,-1,1,-1,1,1,1,-1,1,-1,-1,1,-1,-1,-1,-1,1,-1,1,-1,-1,-1,-1,1,1,-1,1,1,1,-1,1,1,-1,-1,1,1,1,1,1,1,1,1,1,1,-1}
    };
    private static final double[] PREAMBLE = preamble();
    private OfdmCodec() { }

    public static double[] encode(byte[] payload) {
        return RobustOfdmCodec.encode(payload);
    }

    static double[] encodeLegacy(byte[] payload) {
        if (payload == null || payload.length < 1 || payload.length > MAX_PAYLOAD)
            throw new IllegalArgumentException("载荷必须为 1–2048 字节");
        ByteBuffer frame = ByteBuffer.allocate(payload.length + 10);
        frame.put(new byte[] {'S','L','A','1'}).putShort((short) payload.length).put(payload);
        CRC32 crc = new CRC32();
        crc.update(frame.array(), 0, payload.length + 6);
        frame.putInt((int) crc.getValue());
        int blocks = (frame.capacity() * 8 + CARRIERS - 1) / CARRIERS;
        double[] output = Arrays.copyOf(PREAMBLE, (blocks + 2) * SYMBOL);
        int[] values = new int[CARRIERS];
        for (int block = 0; block < blocks; block++) {
            for (int bit = 0; bit < CARRIERS; bit++) {
                int index = block * CARRIERS + bit;
                boolean one = index < frame.capacity() * 8
                        && ((frame.array()[index / 8] >>> (7 - index % 8)) & 1) != 0;
                values[bit] = one ? -1 : 1;
            }
            System.arraycopy(symbol(values), 0, output, (block + 2) * SYMBOL, SYMBOL);
        }
        double peak = 0;
        for (double value : output) peak = Math.max(peak, Math.abs(value));
        for (int i = 0; i < output.length; i++) output[i] = (float) (output[i] * (0.8 / peak));
        return output;
    }

    public static byte[] decode(double[] samples) {
        try { return RobustOfdmCodec.decode(samples); }
        catch (IllegalArgumentException invalidRobustFrame) { return decodeLegacy(samples); }
    }

    private static byte[] decodeLegacy(double[] samples) {
        if (samples == null || samples.length < 3 * SYMBOL || samples.length > WaveFile.MAX_SAMPLES)
            throw new IllegalArgumentException("录音长度无效");
        for (double value : samples) if (!Double.isFinite(value))
            throw new IllegalArgumentException("录音包含非有限数值");
        int offset = locate(samples);
        int blocks = (samples.length - offset) / SYMBOL;
        if (blocks < 3) throw new IllegalArgumentException("OFDM 帧被截断");
        double[] channelReal = new double[CARRIERS], channelImag = new double[CARRIERS];
        byte[] frame = new byte[(blocks - 2) * CARRIERS / 8];
        for (int block = 0; block < blocks; block++) {
            double[] real = Arrays.copyOfRange(samples, offset + block * SYMBOL + PREFIX,
                    offset + (block + 1) * SYMBOL);
            double[] imag = new double[FFT];
            transform(real, imag, false);
            for (int c = 0; c < CARRIERS; c++) {
                int bin = FIRST_BIN + c;
                if (block < 2) {
                    channelReal[c] += real[bin] * TRAINING[block][c] / 2;
                    channelImag[c] += imag[bin] * TRAINING[block][c] / 2;
                } else {
                    double power = channelReal[c] * channelReal[c] + channelImag[c] * channelImag[c];
                    if (power < 1e-16) throw new IllegalArgumentException("音频信道存在不可用载波");
                    if (real[bin] * channelReal[c] + imag[bin] * channelImag[c] < 0) {
                        int bit = (block - 2) * CARRIERS + c;
                        frame[bit / 8] |= (byte) (1 << (7 - bit % 8));
                    }
                }
            }
        }
        if (frame.length < 10 || frame[0] != 'S' || frame[1] != 'L'
                || frame[2] != 'A' || frame[3] != '1') throw new IllegalArgumentException("OFDM 帧头无效");
        ByteBuffer buffer = ByteBuffer.wrap(frame);
        int length = Short.toUnsignedInt(buffer.getShort(4));
        if (length < 1 || length > MAX_PAYLOAD || frame.length < length + 10)
            throw new IllegalArgumentException("OFDM 载荷无效或被截断");
        CRC32 crc = new CRC32();
        crc.update(frame, 0, length + 6);
        if (crc.getValue() != Integer.toUnsignedLong(buffer.getInt(length + 6)))
            throw new IllegalArgumentException("OFDM 校验失败，数据已损坏");
        return Arrays.copyOfRange(frame, 6, length + 6);
    }

    private static int locate(double[] values) {
        int n = 1;
        while (n < values.length + PREAMBLE.length - 1) n <<= 1;
        double[] re = Arrays.copyOf(values, n), im = new double[n];
        double[] pr = new double[n], pi = new double[n];
        double preambleEnergy = 0;
        for (int i = 0; i < PREAMBLE.length; i++) {
            pr[i] = PREAMBLE[PREAMBLE.length - 1 - i];
            preambleEnergy += PREAMBLE[i] * PREAMBLE[i];
        }
        transform(re, im, false);
        transform(pr, pi, false);
        for (int i = 0; i < n; i++) {
            double real = re[i] * pr[i] - im[i] * pi[i];
            im[i] = re[i] * pi[i] + im[i] * pr[i];
            re[i] = real;
        }
        transform(re, im, true);
        double energy = 0, best = -1;
        int bestOffset = 0;
        for (int i = 0; i < PREAMBLE.length; i++) energy += values[i] * values[i];
        for (int start = 0; start <= values.length - PREAMBLE.length; start++) {
            double score = Math.abs(re[start + PREAMBLE.length - 1])
                    / Math.sqrt(Math.max(energy, 1e-20) * preambleEnergy);
            if (score > best) { best = score; bestOffset = start; }
            if (start + PREAMBLE.length < values.length)
                energy += values[start + PREAMBLE.length] * values[start + PREAMBLE.length]
                        - values[start] * values[start];
        }
        if (best < 0.6) throw new IllegalArgumentException("未找到 OFDM 前导信号");
        return bestOffset;
    }

    private static double[] preamble() {
        double[] result = new double[SYMBOL * 2];
        for (int i = 0; i < 2; i++) System.arraycopy(symbol(TRAINING[i]), 0, result, i * SYMBOL, SYMBOL);
        return result;
    }

    static double[] symbol(int[] values) {
        double[] real = new double[FFT], imag = new double[FFT];
        for (int i = 0; i < CARRIERS; i++) real[FIRST_BIN + i] = real[FFT - FIRST_BIN - i] = values[i];
        transform(real, imag, true);
        double[] result = new double[SYMBOL];
        System.arraycopy(real, FFT - PREFIX, result, 0, PREFIX);
        System.arraycopy(real, 0, result, PREFIX, FFT);
        return result;
    }

    /** Iterative radix-2 complex FFT, inverse normalized by n. */
    static void transform(double[] real, double[] imag, boolean inverse) {
        int n = real.length;
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >>> 1;
            for (; (j & bit) != 0; bit >>>= 1) j ^= bit;
            j ^= bit;
            if (i < j) {
                double t = real[i]; real[i] = real[j]; real[j] = t;
                t = imag[i]; imag[i] = imag[j]; imag[j] = t;
            }
        }
        for (int size = 2; size <= n; size <<= 1) {
            double angle = (inverse ? 2 : -2) * Math.PI / size;
            double stepR = Math.cos(angle), stepI = Math.sin(angle);
            for (int base = 0; base < n; base += size) {
                double wr = 1, wi = 0;
                for (int j = 0; j < size / 2; j++) {
                    int a = base + j, b = a + size / 2;
                    double br = real[b] * wr - imag[b] * wi;
                    double bi = real[b] * wi + imag[b] * wr;
                    real[b] = real[a] - br; imag[b] = imag[a] - bi;
                    real[a] += br; imag[a] += bi;
                    double next = wr * stepR - wi * stepI;
                    wi = wr * stepI + wi * stepR; wr = next;
                }
            }
        }
        if (inverse) for (int i = 0; i < n; i++) { real[i] /= n; imag[i] /= n; }
    }
}
