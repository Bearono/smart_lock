package org.smartlock.course;

import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.zip.CRC32;

/** SLA2 long-guard, frequency-diverse repetition. CRC does not authenticate a sender. */
final class RobustOfdmCodec {
    private static final int FFT=256, PREFIX=256, SYMBOL=512, DATA=21, CARRIERS=64;
    private static final double[] PREAMBLE = preamble();
    private RobustOfdmCodec() { }

    static double[] encode(byte[] payload) {
        if (payload==null || payload.length<1 || payload.length>OfdmCodec.MAX_PAYLOAD)
            throw new IllegalArgumentException("载荷必须为 1–2048 字节");
        ByteBuffer packet=ByteBuffer.allocate(payload.length+10);
        packet.put(new byte[]{'S','L','A','2'}).putShort((short)payload.length).put(payload);
        CRC32 crc=new CRC32();crc.update(packet.array(),0,payload.length+6);packet.putInt((int)crc.getValue());
        int blocks=(packet.capacity()*8+DATA-1)/DATA;
        double[] result=Arrays.copyOf(PREAMBLE,(blocks+2)*SYMBOL);
        for(int block=0;block<blocks;block++) {
            int[] values=new int[CARRIERS];values[63]=1;
            for(int bit=0;bit<DATA;bit++) {
                int index=block*DATA+bit;
                int sign=index<packet.capacity()*8 && ((packet.array()[index/8]>>>(7-index%8))&1)!=0 ? -1:1;
                for(int repeat=0;repeat<3;repeat++)values[repeat*DATA+bit]=sign;
            }
            System.arraycopy(symbol(values),0,result,(block+2)*SYMBOL,SYMBOL);
        }
        double peak=0;for(double value:result)peak=Math.max(peak,Math.abs(value));
        for(int i=0;i<result.length;i++)result[i]=(float)(result[i]*(.8/peak));
        return result;
    }

    static byte[] decode(double[] samples) {
        if(samples==null || samples.length<5*SYMBOL || samples.length>WaveFile.MAX_SAMPLES)
            throw new IllegalArgumentException("录音长度无效");
        for(double value:samples)if(!Double.isFinite(value))throw new IllegalArgumentException("录音数值无效");
        double[] scores=scores(samples);
        int[] deltas={0,-16,16,-32,32,-48,48,-64,64};
        for(int attempt=0;attempt<6;attempt++) {
            int center=0;
            for(int i=1;i<scores.length;i++)if(scores[i]>scores[center])center=i;
            if(scores[center]<.15)break;
            Arrays.fill(scores,Math.max(0,center-2*SYMBOL),Math.min(scores.length,center+2*SYMBOL+1),-1.);
            for(int delta:deltas)try{return decodeAt(samples,center+delta);}
                catch(IllegalArgumentException invalidCandidate){/* bounded next timing candidate */}
        }
        throw new IllegalArgumentException("未找到校验完整的 SLA2 音频帧");
    }

    private static double[][] carriers(double[] samples,int offset,int count) {
        if(offset<0 || offset+count*SYMBOL>samples.length)throw new IllegalArgumentException("音频帧被截断");
        double[][] result=new double[count*2][CARRIERS];
        for(int block=0;block<count;block++) {
            double[] real=Arrays.copyOfRange(samples,offset+block*SYMBOL+PREFIX,offset+(block+1)*SYMBOL);
            double[] imag=new double[FFT];OfdmCodec.transform(real,imag,false);
            for(int c=0;c<CARRIERS;c++){result[2*block][c]=real[16+c];result[2*block+1][c]=imag[16+c];}
        }
        return result;
    }

    private static byte[] bytes(double[][] carriers,double[] real,double[] imag) {
        int bits=(carriers.length/2-2)*DATA;
        byte[] packet=new byte[(bits+7)/8];
        double previousPhase=0;
        for(int block=2;block<carriers.length/2;block++) {
            double[] er=new double[63],ei=new double[63];
            for(int c=0;c<63;c++) {
                er[c]=carriers[2*block][c]*real[c]+carriers[2*block+1][c]*imag[c];
                ei[c]=carriers[2*block+1][c]*real[c]-carriers[2*block][c]*imag[c];
            }
            // Cross-band products cancel the repeated BPSK bits and reveal clock drift.
            double crossR=0,crossI=0;
            for(int c=DATA;c<63;c++) {
                crossR+=er[c]*er[c-DATA]+ei[c]*ei[c-DATA];
                crossI+=ei[c]*er[c-DATA]-er[c]*ei[c-DATA];
            }
            double phase=Math.atan2(crossI,crossR);
            while(phase-previousPhase>Math.PI)phase-=2*Math.PI;
            while(phase-previousPhase< -Math.PI)phase+=2*Math.PI;
            previousPhase=phase;
            if(Math.abs(phase*FFT/(2*Math.PI*DATA))>PREFIX/2.)
                throw new IllegalArgumentException("音频时钟偏移超出保护间隔");
            for(int b=0;b<DATA;b++) {
                double soft=0;
                for(int repeat=0;repeat<3;repeat++) {
                    int c=repeat*DATA+b;
                    double angle=phase*(16+c)/DATA;
                    soft+=er[c]*Math.cos(angle)+ei[c]*Math.sin(angle);
                }
                if(soft<0){int bit=(block-2)*DATA+b;packet[bit/8]|=(byte)(1<<(7-bit%8));}
            }
        }
        return packet;
    }

    private static byte[] decodeAt(double[] samples,int offset) {
        double[][] initial=carriers(samples,offset,5);
        double[] real=new double[CARRIERS],imag=new double[CARRIERS];
        double dotR=0,dotI=0,powerA=0,powerB=0;
        for(int c=0;c<CARRIERS;c++) {
            double ar=initial[0][c]*OfdmCodec.TRAINING[0][c],ai=initial[1][c]*OfdmCodec.TRAINING[0][c];
            double br=initial[2][c]*OfdmCodec.TRAINING[1][c],bi=initial[3][c]*OfdmCodec.TRAINING[1][c];
            dotR+=ar*br+ai*bi;dotI+=ar*bi-ai*br;powerA+=ar*ar+ai*ai;powerB+=br*br+bi*bi;
            real[c]=(ar+br)/2;imag[c]=(ai+bi)/2;
        }
        double coherence=Math.hypot(dotR,dotI)/Math.max(Math.sqrt(powerA*powerB),1e-20);
        if(coherence<.85)throw new IllegalArgumentException("训练信号不一致");
        for(int b=0;b<DATA;b++) {
            double power=0;for(int repeat=0;repeat<3;repeat++){int c=repeat*DATA+b;power+=real[c]*real[c]+imag[c]*imag[c];}
            if(power<1e-16)throw new IllegalArgumentException("载波组不可用");
        }
        byte[] header=bytes(initial,real,imag);
        if(header[0]!='S'||header[1]!='L'||header[2]!='A'||header[3]!='2')throw new IllegalArgumentException("帧头无效");
        int length=Short.toUnsignedInt(ByteBuffer.wrap(header).getShort(4));
        if(length<1||length>OfdmCodec.MAX_PAYLOAD)throw new IllegalArgumentException("载荷长度无效");
        int blocks=2+(8*(length+10)+DATA-1)/DATA;
        byte[] packet=bytes(carriers(samples,offset,blocks),real,imag);
        CRC32 crc=new CRC32();crc.update(packet,0,length+6);
        if(crc.getValue()!=Integer.toUnsignedLong(ByteBuffer.wrap(packet).getInt(length+6)))throw new IllegalArgumentException("音频数据损坏");
        return Arrays.copyOfRange(packet,6,length+6);
    }

    private static double[] scores(double[] samples) {
        int n=1;while(n<samples.length+PREAMBLE.length-1)n<<=1;
        double[] re=Arrays.copyOf(samples,n),im=new double[n],pr=new double[n],pi=new double[n];
        double preambleEnergy=0;
        for(int i=0;i<PREAMBLE.length;i++){pr[i]=PREAMBLE[PREAMBLE.length-1-i];preambleEnergy+=PREAMBLE[i]*PREAMBLE[i];}
        OfdmCodec.transform(re,im,false);OfdmCodec.transform(pr,pi,false);
        for(int i=0;i<n;i++){double r=re[i]*pr[i]-im[i]*pi[i];im[i]=re[i]*pi[i]+im[i]*pr[i];re[i]=r;}
        OfdmCodec.transform(re,im,true);
        double energy=0;for(int i=0;i<PREAMBLE.length;i++)energy+=samples[i]*samples[i];
        double[] scores=new double[samples.length-PREAMBLE.length+1];
        for(int start=0;start<scores.length;start++) {
            scores[start]=Math.abs(re[start+PREAMBLE.length-1])/Math.sqrt(Math.max(energy,1e-20)*preambleEnergy);
            if(start+PREAMBLE.length<samples.length)energy+=samples[start+PREAMBLE.length]*samples[start+PREAMBLE.length]-samples[start]*samples[start];
        }
        return scores;
    }

    private static double[] symbol(int[] values) {
        double[] legacy=OfdmCodec.symbol(values),result=new double[SYMBOL];
        System.arraycopy(legacy,64,result,0,FFT);System.arraycopy(legacy,64,result,FFT,FFT);
        return result;
    }
    private static double[] preamble() {
        double[] result=new double[2*SYMBOL];
        for(int i=0;i<2;i++)System.arraycopy(symbol(OfdmCodec.TRAINING[i]),0,result,i*SYMBOL,SYMBOL);
        return result;
    }
}
