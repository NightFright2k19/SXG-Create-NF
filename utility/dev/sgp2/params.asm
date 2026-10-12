; S-YXG2006LE (SGP2.DLL): VST parameters (Reset Mode, SysEx, master settings, Panic) in a new section .sxg
; main hook: eax = AEffect (plugin + 0x20); the AEffect callbacks are replaced, the originals kept
.set NP, 9
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
    lea ecx, [setp_h]
    mov [eax + 0xC], ecx
    lea ecx, [getp]
    mov [eax + 0x10], ecx
    mov dword ptr [eax + 0x18], NP
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


; parameters are kept as integers 0..pmax[i]; the host sees value / pmax[i]
; 0 Reset Mode (None/GM/GS/XGLite/GM2), 1 SysEx (Off/On), 2 Master Volume, 3 Master Tune (cent),
; 4 Transpose (semitones), 5 Reverb Return, 6 Chorus Return, 7 Panic (momentary: all sound/notes off),
; 8 Polyphony (8..64 notes: beyond it the oldest note gets a note-off; the engine itself has 64 voices)
; Parameters 2..6 are sent as XG system/effect SysEx in front of the host events when changed and after each reset.

; eax = parameter index, at most NP - 1
clampi:
    cmp eax, 8
    jbe ci_ok
    mov eax, 8
ci_ok:
    ret

; float getParameter(AEffect*, int idx)
getp:
    mov eax, [esp + 8]
    call clampi
    fild dword ptr [ivals + eax * 4]
    fidiv dword ptr [pmax + eax * 4]
    ret

; host setParameter: snap, then tell the host the snapped value (audioMasterAutomate, audioMasterUpdateDisplay)
; so that its slider jumps to the step even when it ignores effGetParameterProperties
setp_h:
    push dword ptr [esp + 0xC]
    push dword ptr [esp + 0xC]
    push dword ptr [esp + 0xC]
    call setp
    add esp, 0xC
    mov eax, [esp + 8]
    call clampi
    fild dword ptr [ivals + eax * 4]
    fidiv dword ptr [pmax + eax * 4]
    sub esp, 4
    fstp dword ptr [esp]
    pop edx
    cmp edx, [esp + 0xC]
    je sh_ret
    mov ecx, [esp + 4]
    mov ecx, [ecx - 0x14]               ; audioMaster (plugin + 0xC; AEffect is at plugin + 0x20)
    test ecx, ecx
    jz sh_ret
    push ecx
    push edx
    push 0
    push 0
    push eax
    push 0                              ; audioMasterAutomate
    push dword ptr [esp + 0x1C]
    call ecx
    add esp, 0x18
    pop ecx
    push 0
    push 0
    push 0
    push 0
    push 42                             ; audioMasterUpdateDisplay
    push dword ptr [esp + 0x18]
    call ecx
    add esp, 0x18
sh_ret:
    ret

; void setParameter(AEffect*, int idx, float v)
setp:
    mov eax, [esp + 8]
    call clampi
    fld dword ptr [esp + 0xC]
    fimul dword ptr [pmax + eax * 4]
    sub esp, 4
    fistp dword ptr [esp]
    pop ecx
    test ecx, ecx
    jns sp_pos
    xor ecx, ecx
sp_pos:
    cmp ecx, [pmax + eax * 4]
    jbe sp_in
    mov ecx, [pmax + eax * 4]
sp_in:
    cmp eax, 7
    je sp_panic
    cmp ecx, [ivals + eax * 4]
    je sp_ret
    mov [ivals + eax * 4], ecx
    test eax, eax
    jnz sp_dirty
    mov dword ptr [pending], 1
    ret
sp_dirty:
    bts dword ptr [dirty], eax
sp_ret:
    ret
sp_panic:
    test ecx, ecx
    jz sp_ret
    mov dword ptr [panic], 1
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
d_label:
    mov eax, [esp + 0xC]
    call clampi
    mov eax, [labels + eax * 4]
    jmp d_copy
d_name:
    mov eax, [esp + 0xC]
    call clampi
    mov eax, [names + eax * 4]
    jmp d_copy
d_disp:
    mov eax, [esp + 0xC]
    call clampi
    mov ecx, [ivals + eax * 4]
    mov edx, [etab + eax * 4]
    test edx, edx
    jz d_num
    mov eax, [edx + ecx * 4]
    jmp d_copy
d_num:
    sub ecx, [poff + eax * 4]
    lea eax, [numbuf]
    push edi
    lea edi, [numbuf]
    test ecx, ecx
    jns dn_pos
    mov byte ptr [edi], 0x2D
    inc edi
    neg ecx
dn_pos:
    push eax
    mov eax, ecx
    xor ecx, ecx
dn_div:
    xor edx, edx
    push ebx
    mov ebx, 10
    div ebx
    pop ebx
    add dl, 0x30
    push edx
    inc ecx
    test eax, eax
    jnz dn_div
dn_out:
    pop eax
    stosb
    loop dn_out
    mov byte ptr [edi], 0
    pop eax
    pop edi
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

; effGetParameterProperties: VstParameterProperties* in ptr
d_props:
    push edi
    mov edi, [esp + 0x18]
    mov ecx, 0x2A                       ; clear 168 bytes
    xor eax, eax
dp_clr:
    mov [edi + ecx * 4 - 4], eax
    loop dp_clr
    mov eax, [esp + 0x10]
    call clampi
    fld1
    fidiv dword ptr [pmax + eax * 4]
    fst dword ptr [edi]                 ; stepFloat = smallStep = largeStep = 1 / pmax
    fst dword ptr [edi + 4]
    fstp dword ptr [edi + 8]
    mov ecx, [pflag + eax * 4]
    mov [edi + 0x4C], ecx
    mov ecx, [poff + eax * 4]
    neg ecx
    mov [edi + 0x50], ecx               ; minInteger
    add ecx, [pmax + eax * 4]
    mov [edi + 0x54], ecx               ; maxInteger
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

; the plugin itself saves no chunk (size 0) although it sets programsAreChunks: the chunk is ours,
; 'SXR2' + NP parameter integers (older 'SXRS' + Reset Mode and SysEx floats is still read)
d_getchunk:
    push esi
    push edi
    xor ecx, ecx
dgc_loop:
    mov eax, [ivals + ecx * 4]
    mov [chunk + 4 + ecx * 4], eax
    inc ecx
    cmp ecx, NP
    jb dgc_loop
    pop edi
    pop esi
    mov eax, [esp + 0x14]
    lea ecx, [chunk]
    mov [eax], ecx
    mov eax, 4 + 4 * 9
    ret
d_setchunk:
    mov eax, [esp + 0x14]
    mov edx, 9
    cmp dword ptr [eax], 0x33525853      ; 'SXR3': 9 parameters
    je dsc_new
    mov edx, 7
    cmp dword ptr [eax], 0x32525853      ; 'SXR2': 8 parameters (Panic is not restored)
    je dsc_new
    cmp dword ptr [eax], 0x53525853
    jne dsc_no
    cmp dword ptr [esp + 0x10], 12
    jb dsc_no
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
    jmp dsc_set
dsc_new:
    lea ecx, [edx * 4 + 4]
    cmp dword ptr [esp + 0x10], ecx
    jb dsc_no
    push esi
    push edx
    lea esi, [eax + 4]
    xor ecx, ecx
dsc_loop:
    cmp ecx, 7
    je dsc_skip
    mov edx, [esi + ecx * 4]
    cmp edx, [pmax + ecx * 4]
    jbe dsc_ok
    mov edx, [pdef + ecx * 4]
dsc_ok:
    mov [ivals + ecx * 4], edx
dsc_skip:
    inc ecx
    cmp ecx, [esp]
    jb dsc_loop
    pop edx
    pop esi
dsc_set:
    mov dword ptr [pending], 1
    or dword ptr [dirty], 0x7C
dsc_no:
    mov eax, 1
    ret

; append our events at edi (count ebx): the pending reset, changed master settings, Panic
emit:
    cmp dword ptr [pending], 0
    je em_par
    mov dword ptr [pending], 0
    mov dword ptr [ncount], 0
    mov eax, [ivals]
    mov eax, [resets + eax * 4]
    test eax, eax
    jz em_par
    mov [edi], eax
    add edi, 4
    inc ebx
    xor eax, eax
    cmp dword ptr [ivals], 2
    sete al
    mov [gsmode], eax
    or dword ptr [dirty], 0x7C             ; a reset restores the defaults: send ours again
em_par:
    cmp dword ptr [gsmode], 0
    jne em_gs
    mov eax, [ivals + 8]
    mov [sx_vol + 7], al
    mov eax, [ivals + 12]
    imul eax, eax, 10
    add eax, 0x400 - 1000
    mov ecx, eax
    and ecx, 0xF
    mov [sx_tune + 10], cl
    shr eax, 4
    mov ecx, eax
    and ecx, 0xF
    mov [sx_tune + 9], cl
    shr eax, 4
    mov [sx_tune + 8], al
    mov eax, [ivals + 16]
    add eax, 0x28
    mov [sx_trn + 7], al
    mov eax, [ivals + 20]
    mov [sx_rev + 7], al
    mov eax, [ivals + 24]
    mov [sx_cho + 7], al
    lea edx, [pev]
    jmp em_send
; GS mode: the same settings as GS system parameters (Roland checksum)
em_gs:
    mov eax, [ivals + 8]
    mov [gs_vol + 8], al
    mov eax, [ivals + 12]
    imul eax, eax, 10
    add eax, 0x400 - 1000
    mov ecx, eax
    and ecx, 0xF
    mov [gs_tune + 11], cl
    shr eax, 4
    mov ecx, eax
    and ecx, 0xF
    mov [gs_tune + 10], cl
    shr eax, 4
    mov [gs_tune + 9], al
    mov eax, [ivals + 16]
    add eax, 0x28
    mov [gs_trn + 8], al
    mov eax, [ivals + 20]
    mov [gs_rev + 8], al
    mov eax, [ivals + 24]
    mov [gs_cho + 8], al
    mov ecx, 2
gs_ev:
    mov eax, [pev_gs + ecx * 4]
    push ecx
    push esi
    mov esi, [eax + 0x18]
    mov ecx, [eax + 0x10]
    sub ecx, 7                             ; address + data bytes
    xor eax, eax
gs_sum:
    add al, [esi + ecx + 4]
    loop gs_sum
    neg al
    and al, 0x7F
    mov ecx, [esp + 4]
    mov ecx, [pev_gs + ecx * 4]
    mov ecx, [ecx + 0x10]
    mov [esi + ecx - 2], al
    pop esi
    pop ecx
    inc ecx
    cmp ecx, 7
    jb gs_ev
    lea edx, [pev_gs]
em_send:
    mov ecx, 2
em_loop:
    bt dword ptr [dirty], ecx
    jnc em_next
    mov eax, [edx + ecx * 4]
    mov [edi], eax
    add edi, 4
    inc ebx
em_next:
    inc ecx
    cmp ecx, 7
    jb em_loop
    mov dword ptr [dirty], 0
    cmp dword ptr [panic], 0
    je em_ret
    mov dword ptr [panic], 0
    mov dword ptr [ncount], 0
    lea eax, [ev_panic]
    mov ecx, 32
em_pan:
    mov [edi], eax
    add edi, 4
    inc ebx
    add eax, 32
    loop em_pan
em_ret:
    ret

; processEvents: our events in front, host SysEx dropped when SysEx is Off
d_events:
    mov dword ptr [got], 1
    push esi
    push edi
    push ebx
    lea edi, [evlist + 8]            ; our event pointer array
    xor ebx, ebx                     ; count
    call emit
    mov esi, [esp + 0x20]            ; host VstEvents*
    mov ecx, [esi]                   ; numEvents
    lea esi, [esi + 8]
de_loop:
    test ecx, ecx
    jz de_done
    cmp ebx, 1000
    jae de_done
    mov eax, [esi]
    add esi, 4
    dec ecx
    cmp dword ptr [eax], 6           ; kVstSysExType
    jne de_keep
    cmp dword ptr [ivals + 4], 0
    je de_loop                       ; SysEx disabled
    mov [edi], eax
    add edi, 4
    inc ebx
    call is_reset                    ; a reset in the song (GM / GS / XG): send our settings again right after it
    jnz de_loop
    or dword ptr [dirty], 0x7C
    push ecx
    push esi
    mov edx, [eax + 0x18]
    xor ecx, ecx
    cmp byte ptr [edx + 1], 0x41
    sete cl
    mov [gsmode], ecx                ; GS reset: the engine now takes GS parameter SysEx only
    call em_par
    pop esi
    pop ecx
    jmp de_loop
de_keep:
    cmp dword ptr [eax], 1           ; kVstMidiType
    jne de_store
    call poly
de_store:
    mov [edi], eax
    add edi, 4
    inc ebx
    jmp de_loop

; Polyphony: sounding notes as key << 8 | channel, oldest first; a note-on beyond the limit
; first gets a note-off for the oldest note (put into the event list at edi, count ebx)
poly:
    push eax
    push ecx
    push edx
    push esi
    mov edx, [eax + 0x18]            ; midiData
    mov esi, edx
    shr esi, 16
    and esi, 0x7F                    ; velocity / value
    mov eax, edx
    and eax, 0x7F0F                  ; key << 8 | channel
    mov ecx, edx
    and cl, 0xF0
    cmp cl, 0x90
    jne po_n9
    test esi, esi
    jz po_rm
    call rm_id                       ; a retriggered note counts once
po_lim:
    mov ecx, [ivals + 32]
    add ecx, 8
    cmp [ncount], ecx
    jb po_add
    push eax
    mov eax, [notes]
    call rm_id
    call off_ev
    pop eax
    jmp po_lim
po_add:
    mov ecx, [ncount]
    cmp ecx, 64
    jae po_done
    mov [notes + ecx * 4], eax
    inc dword ptr [ncount]
    jmp po_done
po_n9:
    cmp cl, 0x80
    je po_rm
    cmp cl, 0xB0
    jne po_done
    mov ecx, edx
    shr ecx, 8
    and ecx, 0x7F
    cmp ecx, 120                     ; All Sound Off / All Notes Off: the channel is silent
    je po_ch
    cmp ecx, 123
    jne po_done
po_ch:
    and eax, 0xF
    xor ecx, ecx
pc_loop:
    cmp ecx, [ncount]
    jae po_done
    mov edx, [notes + ecx * 4]
    and edx, 0xF
    cmp edx, eax
    jne pc_next
    push eax
    mov eax, [notes + ecx * 4]
    call rm_id
    pop eax
    jmp pc_loop
pc_next:
    inc ecx
    jmp pc_loop
po_rm:
    call rm_id
po_done:
    pop esi
    pop edx
    pop ecx
    pop eax
    ret

; remove note eax from the list
rm_id:
    push ecx
    push edx
    xor ecx, ecx
ri_find:
    cmp ecx, [ncount]
    jae ri_ret
    cmp [notes + ecx * 4], eax
    je ri_del
    inc ecx
    jmp ri_find
ri_del:
    dec dword ptr [ncount]
ri_shift:
    cmp ecx, [ncount]
    jae ri_ret
    mov edx, [notes + ecx * 4 + 4]
    mov [notes + ecx * 4], edx
    inc ecx
    jmp ri_shift
ri_ret:
    pop edx
    pop ecx
    ret

; append a note-off for note eax at edi (count ebx)
off_ev:
    push ecx
    push edx
    mov ecx, [offi]
    inc dword ptr [offi]
    and ecx, 63
    shl ecx, 5
    lea edx, [ev_off + ecx]
    mov dword ptr [edx], 1
    mov dword ptr [edx + 4], 32
    mov ecx, eax
    and ecx, 0x7F0F
    or ecx, 0x80
    mov [edx + 0x18], ecx
    mov [edi], edx
    add edi, 4
    inc ebx
    pop edx
    pop ecx
    ret

; ZF = 1 when the VstSysExEvent eax is a GM / GM2 / GS / XG reset
is_reset:
    push edx
    mov edx, [eax + 0x18]            ; sysexDump
    cmp dword ptr [eax + 0x10], 6
    jb ir_no
    cmp byte ptr [edx + 1], 0x7E     ; F0 7E xx 09: GM On / Off / GM2 On
    jne ir_gs
    cmp byte ptr [edx + 3], 0x09
    jmp ir_ret
ir_gs:
    cmp byte ptr [edx + 1], 0x41     ; F0 41 xx 42 12 40 00 7F: GS reset
    jne ir_xg
    cmp dword ptr [eax + 0x10], 8
    jb ir_no
    cmp dword ptr [edx + 3], 0x00401242
    jne ir_ret
    cmp byte ptr [edx + 7], 0x7F
    jmp ir_ret
ir_xg:
    cmp byte ptr [edx + 1], 0x43     ; F0 43 1x 4C 00 00 7E / 7F: XG System On / All Parameter Reset
    jne ir_ret
    cmp dword ptr [eax + 0x10], 7
    jb ir_no
    cmp word ptr [edx + 3], 0x004C
    jne ir_ret
    cmp byte ptr [edx + 5], 0
    jne ir_ret
    mov dl, [edx + 6]
    or dl, 1
    cmp dl, 0x7F
    jmp ir_ret
ir_no:
    or edx, 1                        ; ZF = 0 (edx != 0)
ir_ret:
    pop edx
    ret
de_done:
    mov [evlist], ebx
    pop ebx
    pop edi
    pop esi
    lea eax, [evlist]
    mov [esp + 0x14], eax
    jmp dword ptr [orig_disp]

; process / processReplacing: send our pending events when the host sent none this block
repl:
    mov eax, [orig_repl]
    jmp p_common
proc:
    mov eax, [orig_proc]
p_common:
    mov [p_target], eax
    cmp dword ptr [got], 0
    jne p_go
    push edi
    push ebx
    lea edi, [evlist + 8]
    xor ebx, ebx
    call emit
    mov [evlist], ebx
    test ebx, ebx
    pop ebx
    pop edi
    jz p_go
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

.align 4
names: .int s_reset, s_sysex, s_vol, s_tune, s_trn, s_rev, s_cho, s_panic, s_poly
labels: .int s_empty, s_empty, s_empty, s_cent, s_semi, s_empty, s_empty, s_empty, s_empty
pmax: .int 4, 1, 127, 200, 48, 127, 127, 1, 56
pdef: .int 3, 1, 127, 100, 24, 64, 64, 0, 56
poff: .int 0, 0, 0, 100, 24, 0, 0, 0, -8
pflag: .int 0xE, 0xF, 0xE, 0xE, 0xE, 0xE, 0xE, 0xF, 0xE   ; IsSwitch 1, IntMinMax 2, FloatStep 4, IntStep 8
etab: .int modes, offon, 0, 0, 0, 0, 0, panics, 0
pev: .int 0, 0, ev_vol, ev_tune, ev_trn, ev_rev, ev_cho, 0, 0
pev_gs: .int 0, 0, eg_vol, eg_tune, eg_trn, eg_rev, eg_cho, 0, 0
modes: .int s_none, s_gm, s_gs, s_xgl, s_gm2
offon: .int s_off, s_on
panics: .int s_dash, s_panic
resets: .int 0, ev_gm, ev_gs, ev_xg, ev_gm2
s_reset: .asciz "Reset Mode"
s_kernel: .asciz "KERNEL32.dll"
s_find: .asciz "FindResourceA"
s_load: .asciz "LoadResource"
s_size: .asciz "SizeofResource"
s_sysex: .asciz "SysEx"
s_vol: .asciz "Master Volume"
s_tune: .asciz "Master Tune"
s_trn: .asciz "Transpose"
s_rev: .asciz "Reverb Return"
s_cho: .asciz "Chorus Return"
s_panic: .asciz "Panic"
s_poly: .asciz "Polyphony"
s_cent: .asciz "cent"
s_semi: .asciz "semi"
s_dash: .asciz "-"
s_empty: .byte 0
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
ev_vol: .int 6, 32, 0, 0, 9, 0, sx_vol, 0
ev_tune: .int 6, 32, 0, 0, 12, 0, sx_tune, 0
ev_trn: .int 6, 32, 0, 0, 9, 0, sx_trn, 0
ev_rev: .int 6, 32, 0, 0, 9, 0, sx_rev, 0
ev_cho: .int 6, 32, 0, 0, 9, 0, sx_cho, 0
eg_vol: .int 6, 32, 0, 0, 11, 0, gs_vol, 0
eg_tune: .int 6, 32, 0, 0, 14, 0, gs_tune, 0
eg_trn: .int 6, 32, 0, 0, 11, 0, gs_trn, 0
eg_rev: .int 6, 32, 0, 0, 11, 0, gs_rev, 0
eg_cho: .int 6, 32, 0, 0, 11, 0, gs_cho, 0
; VstMidiEvent: type 1, byteSize 32, deltaFrames, flags, noteLength, noteOffset, midiData, detune...
; All Sound Off (CC 120) and All Notes Off (CC 123) on all 16 channels
ev_panic:
    .int 1, 32, 0, 0, 0, 0, 0x78b0, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb0, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b1, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb1, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b2, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb2, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b3, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb3, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b4, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb4, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b5, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb5, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b6, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb6, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b7, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb7, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b8, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb8, 0
    .int 1, 32, 0, 0, 0, 0, 0x78b9, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bb9, 0
    .int 1, 32, 0, 0, 0, 0, 0x78ba, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bba, 0
    .int 1, 32, 0, 0, 0, 0, 0x78bb, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bbb, 0
    .int 1, 32, 0, 0, 0, 0, 0x78bc, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bbc, 0
    .int 1, 32, 0, 0, 0, 0, 0x78bd, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bbd, 0
    .int 1, 32, 0, 0, 0, 0, 0x78be, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bbe, 0
    .int 1, 32, 0, 0, 0, 0, 0x78bf, 0
    .int 1, 32, 0, 0, 0, 0, 0x7bbf, 0
sx_gm: .byte 0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7
sx_gm2: .byte 0xF0, 0x7E, 0x7F, 0x09, 0x03, 0xF7
sx_gs: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41, 0xF7
sx_xg: .byte 0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00, 0xF7
sx_vol: .byte 0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x04, 0x7F, 0xF7
sx_tune: .byte 0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0xF7
sx_trn: .byte 0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x06, 0x40, 0xF7
sx_rev: .byte 0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x0C, 0x40, 0xF7
sx_cho: .byte 0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x2C, 0x40, 0xF7
gs_vol: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x04, 0x7F, 0x00, 0xF7
gs_tune: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0xF7
gs_trn: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x05, 0x40, 0x00, 0xF7
gs_rev: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x01, 0x33, 0x40, 0x00, 0xF7
gs_cho: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x01, 0x3A, 0x40, 0x00, 0xF7
.align 4
ivals: .int 3, 1, 127, 100, 24, 64, 64, 0, 56     ; = pdef
pending: .int 1
dirty: .int 0
gsmode: .int 0
panic: .int 0
got: .int 0
p_target: .int 0
orig_disp: .int 0
k_find: .int 0
k_load: .int 0
k_size: .int 0
orig_repl: .int 0
orig_proc: .int 0
numbuf: .space 16
ncount: .int 0
offi: .int 0
notes: .space 4 * 64
ev_off: .space 32 * 64
chunk: .int 0x33525853
.space 4 * 9
evlist: .int 0, 0
.space 4096
