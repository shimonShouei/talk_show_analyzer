"""Download historical Anthropic message-batch results to raw/*.json.

Needs ANTHROPIC_API_KEY in the environment (the SDK reads it; this file has no key).
The batch ids below are the November 2026 chunk-analysis batches. Output is raw
model text and is gitignored. Do not commit raw/.
"""
import anthropic, json, sys
c=anthropic.Anthropic()
for name,bid in [("hour1_chunks","msgbatch_01V48osVMN9RYQhTxdpDNGRE"),("hour2_chunks","msgbatch_011E6rYSpWaiNpqjsz4m6YYE"),
                 ("haiku5c_chunks","msgbatch_011cTYrNCDbEBmp3sQpas5gu")]:
    out=[]
    for r in c.messages.batches.results(bid):
        d={"custom_id":r.custom_id,"type":r.result.type}
        if r.result.type=="succeeded":
            m=r.result.message; d["text"]="".join(b.text for b in m.content if b.type=="text"); d["stop"]=m.stop_reason
        out.append(d)
    json.dump(out,open(f"raw/{name}.json","w"),ensure_ascii=False,indent=1)
    print(name,len(out),[ (o["custom_id"],o.get("stop")) for o in out][:16])
