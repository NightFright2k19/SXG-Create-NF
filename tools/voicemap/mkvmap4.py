import keystone, sys
ks=keystone.Ks(keystone.KS_ARCH_X86,keystone.KS_MODE_32)
B=0x10000000; CAVE=0x3F6B0
SRC=open(sys.argv[2]).read()
d=open(sys.argv[1],'rb').read()
names=['vm_init','vm_apply','dlg_init','dlg_default','dlg_common','cmd_hook','apply_hook','get_hook','get_orig','set_hook','key']
blocks=[]; cur=None
for line in SRC.split('\n'):
    t=line.strip()
    hit=[n for n in names if t.startswith(n+':')]
    if hit:
        cur=[hit[0],[]]; blocks.append(cur); rest=t[len(hit[0])+1:].strip()
        if rest: cur[1].append(rest)
    elif cur is not None: cur[1].append(line)
def assemble(addrs):
    out=b''; pos={}
    for name,lines in blocks:
        a=B+CAVE+len(out); pos[name]=a
        txt='\n'.join(lines)
        for n,v in addrs.items(): txt=txt.replace('@'+n+'@',hex(v))
        txt=txt.replace('jmp dlg_common','jmp @dlg_common@')
        for n,v in addrs.items(): txt=txt.replace('@'+n+'@',hex(v))
        c,_=ks.asm(txt,a) if txt.strip() else ([],0)
        out+=bytes(c)
    return out,pos
code,pos=assemble({n:0x10040000 for n in names})
for _ in range(10):
    code2,pos2=assemble(pos)
    if code2==code and pos2==pos: break
    code,pos=code2,pos2
else: raise SystemExit('no convergence')
def site(off, asm, n):
    c,_=ks.asm(asm,B+off); c=bytes(c); assert len(c)<=n; return off, d[off:off+n], c+b'\x90'*(n-len(c))
sites=[site(0x3875,f"call {pos['vm_init']:#x}",5), site(0x30b91,f"call {pos['dlg_init']:#x}",5),
       site(0x30c5f,f"call {pos['dlg_default']:#x}",5), site(0x30bef,f"jmp {pos['cmd_hook']:#x}",14),
       site(0x30bba,f"jmp {pos['apply_hook']:#x}",7), site(0x2b50,f"jmp {pos['get_hook']:#x}",6),
       site(0x2bb0,f"jmp {pos['set_hook']:#x}",6)]
print('SYXG50_VOICEMAP = [')
for off,old,new in sites: print(f"    (0x{off:05X}, '{old.hex(' ')}',\n              '{new.hex(' ')}'),")
print(f"    (0x{CAVE:05X}, '{('00 '*len(code)).strip()}',\n              '{code.hex(' ')}'),")
print(']'); print(f'VMAP_CAVE_END = 0x{CAVE+len(code):05X}')
print({k:hex(v) for k,v in pos.items()}, file=sys.stderr)
