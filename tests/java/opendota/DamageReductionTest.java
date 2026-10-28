package opendota;
import java.util.*;
public class DamageReductionTest {
 static Entry entry(Double[] pre,Double[] post,int time){Entry e=new Entry(time);e.type="interval";e.slot=0;e.damage_received_pre_reduction_by_type=pre;e.damage_received_post_reduction_by_type=post;return e;}
 static void check(boolean ok){if(!ok)throw new AssertionError();}
 public static void main(String[] args){
 CreateParsedDataBlob parser=new CreateParsedDataBlob();ParsedData data=new ParsedData();
 parser.applyDamageReduction(List.of(entry(new Double[]{66578.9453125,62826.953125,2208.75},new Double[]{19503.,36985.,2002.},2),entry(new Double[]{1.,0.,0.},new Double[]{0.,0.,0.},1)),data);
 check(data.players.get(0).damage_received_pre_reduction==131612);check(data.players.get(0).damage_prevented==73122);check(Math.round(data.players.get(0).damage_reduction_pct*10)==556);
 parser.applyDamageReduction(List.of(entry(new Double[]{1.,null,0.},new Double[]{0.,0.,0.},3)),data);check(data.players.get(0).damage_received_pre_reduction==131612);
 parser.applyDamageReduction(List.of(entry(new Double[]{0.,0.,0.},new Double[]{0.,0.,0.},4)),data);check(data.players.get(0).damage_reduction_pct==null);
 parser.applyDamageReduction(List.of(entry(new Double[]{100.,0.,0.},new Double[]{120.,0.,0.},5)),data);check(data.players.get(0).damage_reduction_pct<0);
 check(data.players.get(1).damage_reduction_source==null);System.out.println("PASS: Java native damage-counter regression checks");
 }
}
