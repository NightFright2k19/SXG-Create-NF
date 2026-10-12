; S-YXG2006LE (SGP2.DLL): two VST parameters, Reset Mode and SysEx, in a new section .sxg
; main hook: eax = AEffect (plugin + 0x20); the AEffect callbacks are replaced, the originals kept
sec:
main_hook:
    lea eax, [esi + 0x20]
    mov ecx, [eax + 4]
    mov [orig_disp], ecx
    mov ecx, [eax + 0x50]
    mov [orig_repl], ecx
    mov ecx, [eax + 8]
    mov [orig_proc], ecx
    lea ecx, [disp]
    mov [eax + 4], ecx
    lea ecx, [repl]
    mov [eax + 0x50], ecx
    lea ecx, [proc]
    mov [eax + 8], ecx
    lea ecx, [setp]
    mov [eax + 0xC], ecx
    lea ecx, [getp]
    mov [eax + 0x10], ecx
    mov dword ptr [eax + 0x18], 2
    mov ecx, [esp + 4]
    jmp IMG + 0x2cfb

; --embed: the table loaders (file size 0x1004c780, read whole file 0x1004c7d0) take sxgbnw6l.tbl / sxgdat6l.tbl
; from RT_RCDATA resources of the same name (upper case) when present, else from the file as before
fs_hook:
    mov eax, [esp + 4]
    call find_res
    test eax, eax
    jz fs_file
    mov ecx, [esp + 8]
    mov [ecx], edx
    mov al, 1
    ret
fs_file:
    mov eax, [esp + 4]
    push ebx
    push esi
    jmp IMG + 0x4c786
fr_hook:
    mov eax, [esp + 4]
    call find_res
    test eax, eax
    jz fr_file
    push esi
    push edi
    mov esi, eax
    mov edi, [esp + 0x10]
    mov ecx, [esp + 0x14]
    cmp ecx, edx
    jbe fr_n
    mov ecx, edx
fr_n:
    rep movsb
    pop edi
    pop esi
    mov al, 1
    ret
fr_file:
    mov eax, [esp + 4]
    push ebx
    push esi
    jmp IMG + 0x4c7d6

; eax = file path -> eax = resource data (0 if none), edx = size
find_res:
    push ebx
    push esi
    mov esi, eax
    mov ebx, eax
fr_scan:
    mov al, [esi]
    inc esi
    test al, al
    jz fr_scanned
    cmp al, 0x5C
    je fr_sep
    cmp al, 0x2F
    jne fr_scan
fr_sep:
    mov ebx, esi
    jmp fr_scan
fr_scanned:
    cmp dword ptr [k_find], 0
    jne fr_have
    lea eax, [s_kernel]
    push eax
    call dword ptr [IMG + 0x57040]          ; GetModuleHandleA
    mov esi, eax
    lea eax, [s_find]
    push eax
    push esi
    call dword ptr [IMG + 0x5703c]          ; GetProcAddress
    mov [k_find], eax
    lea eax, [s_load]
    push eax
    push esi
    call dword ptr [IMG + 0x5703c]
    mov [k_load], eax
    lea eax, [s_size]
    push eax
    push esi
    call dword ptr [IMG + 0x5703c]
    mov [k_size], eax
fr_have:
    cmp dword ptr [k_find], 0
    je fr_none
    push 10                                 ; RT_RCDATA
    push ebx
    lea eax, [IMG]
    push eax
    call dword ptr [k_find]
    test eax, eax
    jz fr_none
    mov esi, eax
    push eax
    lea eax, [IMG]
    push eax
    call dword ptr [k_size]
    mov ebx, eax
    push esi
    lea eax, [IMG]
    push eax
    call dword ptr [k_load]                 ; LoadResource: the data pointer on Win32 (LockResource is a no-op)
    mov edx, ebx
    pop esi
    pop ebx
    ret
fr_none:
    xor eax, eax
    pop esi
    pop ebx
    ret

; float getParameter(AEffect*, int idx)
getp:
    mov eax, [esp + 8]
    and eax, 1
    fld dword ptr [vals + eax * 4]
    ret

; void setParameter(AEffect*, int idx, float v)
setp:
    mov eax, [esp + 8]
    and eax, 1
    mov ecx, [esp + 0xC]
    mov [vals + eax * 4], ecx
    test eax, eax
    jnz sp_sx
    call mode_idx
    push eax
    fild dword ptr [esp]
    fmul dword ptr [quarter]
    fstp dword ptr [vals]               ; snap to 0/0.25/0.5/0.75/1
    pop eax
    cmp eax, [mode]
    je sp_ret
    mov [mode], eax
    mov dword ptr [pending], 1
sp_ret:
    ret
sp_sx:
    xor eax, eax
    cmp ecx, 0x3F000000                 ; float >= 0.5 (negatives are < as int)
    jl sp_sx0
    mov eax, 0x3F800000
sp_sx0:
    mov [vals + 4], eax
    ret

; eax = Reset Mode index 0..4 from vals[0]
mode_idx:
    fld dword ptr [vals]
    fmul dword ptr [four]
    sub esp, 4
    fistp dword ptr [esp]
    pop eax
    cmp eax, 4
    jbe mi_ok
    mov eax, 4
mi_ok:
    ret

; dispatcher(AEffect*, op, idx, val, ptr, opt)
disp:
    mov eax, [esp + 8]
    cmp eax, 8
    je d_name
    cmp eax, 7
    je d_disp
    cmp eax, 6
    je d_label
    cmp eax, 12
    jne d_not_mains
    cmp dword ptr [esp + 0x10], 0
    je d_pass
    mov dword ptr [pending], 1
    jmp d_pass
d_not_mains:
    cmp eax, 25
    je d_events
    cmp eax, 23
    je d_getchunk
    cmp eax, 24
    je d_setchunk
    cmp eax, 26
    je d_one
    cmp eax, 56
    je d_props
d_pass:
    jmp dword ptr [orig_disp]
d_one:
    mov eax, 1
    ret
; effGetParameterProperties: VstParameterProperties* in ptr
d_props:
    push edi
    mov edi, [esp + 0x18]
    push edi
    mov ecx, 0x2A                       ; clear 168 bytes
    xor eax, eax
    rep stosd
    pop edi
    mov eax, [esp + 0x10]
    and eax, 1
    jnz dp_sx
    mov dword ptr [edi], 0x3E800000     ; stepFloat 0.25
    mov dword ptr [edi + 4], 0x3E800000
    mov dword ptr [edi + 8], 0x3E800000
    mov dword ptr [edi + 0x4C], 0xE     ; IntMinMax|FloatStep|IntStep
    mov dword ptr [edi + 0x54], 4
    jmp dp_common
dp_sx:
    mov dword ptr [edi], 0x3F800000
    mov dword ptr [edi + 4], 0x3F800000
    mov dword ptr [edi + 8], 0x3F800000
    mov dword ptr [edi + 0x4C], 0xF     ; IsSwitch|IntMinMax|FloatStep|IntStep
    mov dword ptr [edi + 0x54], 1
dp_common:
    mov dword ptr [edi + 0x58], 1
    mov dword ptr [edi + 0x5C], 1
    push esi
    mov esi, [names + eax * 4]
    lea edi, [edi + 0xC]
dp_cp:
    lodsb
    stosb
    test al, al
    jnz dp_cp
    pop esi
    pop edi
    mov eax, 1
    ret
d_label:
    mov eax, [esp + 0x14]
    mov byte ptr [eax], 0
    xor eax, eax
    ret
d_name:
    mov eax, [esp + 0xC]
    and eax, 1
    mov eax, [names + eax * 4]
    jmp d_copy
d_disp:
    mov eax, [esp + 0xC]
    and eax, 1
    jnz d_sx
    call mode_idx
    mov eax, [modes + eax * 4]
    jmp d_copy
d_sx:
    lea eax, [s_off]
    fld dword ptr [vals + 4]
    fcomp dword ptr [half]
    fnstsw word ptr [ax_save]
    jmp d_copy_sx
d_copy_sx:
    push ecx
    mov cx, [ax_save]
    test ch, 1                       ; C0 set: value < 0.5
    pop ecx
    jnz d_copy
    lea eax, [s_on]
d_copy:
    push esi
    push edi
    mov esi, eax
    mov edi, [esp + 0x1C]
dc_loop:
    lodsb
    stosb
    test al, al
    jnz dc_loop
    pop edi
    pop esi
    xor eax, eax
    ret

; the plugin itself saves no chunk (size 0) although it sets programsAreChunks: the chunk is ours,
; 'SXRS', Reset Mode value, SysEx value (floats)
d_getchunk:
    mov eax, [vals]
    mov [chunk + 4], eax
    mov eax, [vals + 4]
    mov [chunk + 8], eax
    mov eax, [esp + 0x14]
    lea ecx, [chunk]
    mov [eax], ecx
    mov eax, 12
    ret
d_setchunk:
    cmp dword ptr [esp + 0x10], 12
    jb dsc_no
    mov eax, [esp + 0x14]
    cmp dword ptr [eax], 0x53525853
    jne dsc_no
    push dword ptr [eax + 4]
    push 0
    push dword ptr [esp + 0xC]
    call setp
    add esp, 0xC
    mov eax, [esp + 0x14]
    push dword ptr [eax + 8]
    push 1
    push dword ptr [esp + 0xC]
    call setp
    add esp, 0xC
    mov dword ptr [pending], 1
dsc_no:
    mov eax, 1
    ret

; processEvents: drop SysEx when disabled, put a pending reset in front
d_events:
    mov dword ptr [got], 1
    push esi
    push edi
    push ebx
    mov esi, [esp + 0x20]            ; host VstEvents*
    lea edi, [evlist + 8]            ; our event pointer array
    xor ebx, ebx                     ; count
    cmp dword ptr [pending], 0
    je de_copy
    call reset_ev
    test eax, eax
    jz de_nores
    mov [edi], eax
    add edi, 4
    inc ebx
de_nores:
    mov dword ptr [pending], 0
de_copy:
    mov ecx, [esi]                   ; numEvents
    lea esi, [esi + 8]
de_loop:
    test ecx, ecx
    jz de_done
    cmp ebx, 1020
    jae de_done
    mov eax, [esi]
    add esi, 4
    dec ecx
    cmp dword ptr [eax], 6           ; kVstSysExType
    jne de_keep
    fld dword ptr [vals + 4]
    fcomp dword ptr [half]
    fnstsw word ptr [ax_save]
    push ecx
    mov cx, [ax_save]
    test ch, 1
    pop ecx
    jnz de_loop                      ; SysEx disabled
de_keep:
    mov [edi], eax
    add edi, 4
    inc ebx
    jmp de_loop
de_done:
    mov [evlist], ebx
    pop ebx
    pop edi
    pop esi
    lea eax, [evlist]
    mov [esp + 0x14], eax
    jmp dword ptr [orig_disp]

; eax = VstSysExEvent* for the current Reset Mode, 0 for None
reset_ev:
    mov eax, [mode]
    mov eax, [resets + eax * 4]
    ret

; process / processReplacing: inject a pending reset when the host sent no events this block
repl:
    mov eax, [orig_repl]
    jmp p_common
proc:
    mov eax, [orig_proc]
p_common:
    mov [p_target], eax
    cmp dword ptr [got], 0
    jne p_go
    cmp dword ptr [pending], 0
    je p_go
    call reset_ev
    mov dword ptr [pending], 0
    test eax, eax
    jz p_go
    mov [evlist + 8], eax
    mov dword ptr [evlist], 1
    push 0
    lea ecx, [evlist]
    push ecx
    push 0
    push 0
    push 25
    push dword ptr [esp + 0x18]
    call dword ptr [orig_disp]
    add esp, 0x18
p_go:
    mov dword ptr [got], 0
    jmp dword ptr [p_target]

four: .float 4.0
half: .float 0.5
names: .int s_reset, s_sysex
modes: .int s_none, s_gm, s_gs, s_xgl, s_gm2
resets: .int 0, ev_gm, ev_gs, ev_xg, ev_gm2
s_reset: .asciz "Reset Mode"
s_kernel: .asciz "KERNEL32.dll"
s_find: .asciz "FindResourceA"
s_load: .asciz "LoadResource"
s_size: .asciz "SizeofResource"
s_sysex: .asciz "SysEx"
s_none: .asciz "None"
s_gm: .asciz "GM"
s_gs: .asciz "GS"
s_xgl: .asciz "XGLite"
s_gm2: .asciz "GM2"
s_on: .asciz "On"
s_off: .asciz "Off"
.align 4
; VstSysExEvent: type 6, byteSize 32, deltaFrames, flags, dumpBytes, resvd1, sysexDump*, resvd2
ev_gm: .int 6, 32, 0, 0, 6, 0, sx_gm, 0
ev_gs: .int 6, 32, 0, 0, 11, 0, sx_gs, 0
ev_xg: .int 6, 32, 0, 0, 9, 0, sx_xg, 0
ev_gm2: .int 6, 32, 0, 0, 6, 0, sx_gm2, 0
sx_gm: .byte 0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7
sx_gm2: .byte 0xF0, 0x7E, 0x7F, 0x09, 0x03, 0xF7
sx_gs: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41, 0xF7
sx_xg: .byte 0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00, 0xF7
.align 4
quarter: .float 0.25
vals: .float 0.75, 1.0                ; defaults: XGLite, SysEx on
mode: .int 3
pending: .int 1
got: .int 0
ax_save: .int 0
p_target: .int 0
orig_disp: .int 0
k_find: .int 0
k_load: .int 0
k_size: .int 0
orig_repl: .int 0
orig_proc: .int 0
chunk: .int 0x53525853, 0, 0
evlist: .int 0, 0
.space 4096
