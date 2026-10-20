; S-YXG2006LE (SGP2.DLL): VST parameters (Polyphony, effects, master settings, Send Reset) in a new
; section .sxg, in the order of the S-YXG50 plugins' Settings page
; main hook: eax = AEffect (plugin + 0x20); the AEffect callbacks are replaced, the originals kept
.set NP, 7
.set NE, 8
.set DIRTY_ALL, 0x36                 ; parameters sent as SysEx: Reverb, Chorus, Master Tune, Transpose
sec:
main_hook:
    lea eax, [esi + 0x20]
    cmp dword ptr [creating], 0
    jne mh_plain                     ; engine 2: left as it is
    mov [eng], eax
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
    or dword ptr [eax + 0x24], 1         ; effFlagsHasEditor (editor.c, issue #39)
mh_plain:
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
; 0 Polyphony (8..256 notes: beyond it a new note is dropped; each engine has 32 voices, above 32 the
;   further engines, up to 8, take the overflow), 1 Reverb (CC 91) and 2 Chorus (CC 93) Off / On (Off: the
;   effect return is set to 0, On: to the default 64; the 2006LE has no variation effect, CC 94 does nothing),
; 3 Master Volume -12 ... +12 dB in 0.5 dB steps (output gain, like the Output Level of the MU plugins),
; 4 Master Tune (cent), 5 Transpose (semitones), 6 Send Reset (MT-32 / GM / GS / XGLite / GM2, one-shot)
; Reverb, Chorus, Master Tune and Transpose are sent as XG (after a GS reset: GS) system / effect SysEx in front
; of the host events when changed and after each reset.
; Send Reset (issue #37): MT-32 / GM / GS / XGLite / GM2; choosing a value sends that reset once (MT-32: the GS
; reset plus the part settings of Falcosoft's GS MT-32 sequence, dev/gui/mt32.syx). It shows XGLite after
; loading and nothing is sent then; it is not restored from the plugin state. Resets and all other SysEx from the
; host always pass.

; eax = parameter index, at most NP - 1
clampi:
    cmp eax, NP - 1
    jbe ci_ok
    mov eax, NP - 1
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
    cmp ecx, [ivals + eax * 4]
    je sp_ret
    mov [ivals + eax * 4], ecx
    cmp eax, 6
    jne sp_dirty
    mov dword ptr [pending], 1
    ret
sp_dirty:
    bts dword ptr [dirty], eax
sp_ret:
    ret
; dispatcher(AEffect*, op, idx, val, ptr, opt)
disp:
    mov eax, [esp + 8]
    cmp eax, 10
    jne d_n10
    mov ecx, [esp + 0x18]
    mov [srv], ecx
    jmp d_fwd
d_n10:
    cmp eax, 11
    jne d_n11
    mov ecx, [esp + 0x10]
    mov [bsv], ecx
    jmp d_fwd
d_n11:
    cmp eax, 1
    je d_fwd
    cmp eax, 8
    je d_name
    cmp eax, 7
    je d_disp
    cmp eax, 6
    je d_label
    cmp eax, 12
    jne d_not_mains
    cmp dword ptr [esp + 0x10], 0
    je d_fwd
    call mkx
    jmp d_fwd
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
    cmp eax, 13
    je d_edrect
    cmp eax, 14
    je d_edopen
    cmp eax, 15
    je d_edclose
    cmp eax, 19
    je d_edidle
    cmp eax, 45
    je d_ename
    cmp eax, 47
    je d_evendor
    cmp eax, 48
    je d_eprod
d_pass:
    jmp dword ptr [orig_disp]
; editor (issue #39): effEditGetRect / Open / Close / Idle go to the C code of editor.c (blob after the data,
; entries 8 bytes apart: getrect, open, close, idle); open gets the load address as third argument
d_edrect:
    push dword ptr [esp + 0x14]
    push dword ptr [esp + 8]
    lea eax, [ed_blob]
    call eax
    add esp, 8
    ret
d_edopen:
    lea eax, [ed_share]
    push eax
    lea eax, [IMG]
    push eax
    push dword ptr [esp + 0x1C]
    push dword ptr [esp + 0x10]
    lea eax, [ed_blob + 8]
    call eax
    add esp, 16
    ret
d_edclose:
    push dword ptr [esp + 4]
    lea eax, [ed_blob + 16]
    call eax
    add esp, 4
    xor eax, eax
    ret
d_edidle:
    push dword ptr [esp + 4]
    lea eax, [ed_blob + 24]
    call eax
    add esp, 4
    xor eax, eax
    ret
; the original DLL answers effGetEffectName / VendorString / ProductString with empty strings, so hosts show no name
; (Falcosoft MIDI Player shows product string + version); the MU plugins carry their names in the string table
d_ename:
    lea ecx, [str_name]
    jmp d_estr
d_evendor:
    lea ecx, [str_vendor]
    jmp d_estr
d_eprod:
    lea ecx, [str_product]
d_estr:
    mov edx, [esp + 0x14]
d_estr_loop:
    mov al, [ecx]
    mov [edx], al
    inc ecx
    inc edx
    test al, al
    jne d_estr_loop
    mov eax, 1
    ret
; open / close, sample rate, block size, mains: engine 2 gets them too
d_fwd:
    push esi
    mov esi, 1
df_loop:
    cmp dword ptr [eng + esi * 4], 0
    je df_next
    push dword ptr [esp + 0x1C]
    push dword ptr [esp + 0x1C]
    push dword ptr [esp + 0x1C]
    push dword ptr [esp + 0x1C]
    push dword ptr [esp + 0x1C]
    push dword ptr [eng + esi * 4]
    call dword ptr [orig_disp]
    add esp, 0x18
    cmp dword ptr [esp + 0xC], 1
    jne df_next
    mov dword ptr [eng + esi * 4], 0     ; effClose: the engine has deleted itself
    mov dword ptr [awake + esi * 4], 0
df_next:
    inc esi
    cmp esi, NE
    jb df_loop
    pop esi
    jmp d_pass
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
; 'SXR6' + NP parameter integers ('SXR5' / 'SXR4' of test builds 10-13 are read); older chunks ('SXR3' 9, 'SXR2' 8 parameters in the old order Reset Mode,
; SysEx, Master Volume 0-127, Tune, Transpose, Reverb / Chorus Return, Panic, Polyphony 8-128) are converted
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
    mov eax, 4 + 4 * NP
    ret
d_setchunk:
    mov eax, [esp + 0x14]
    push esi
    lea esi, [eax + 4]
    cmp dword ptr [eax], 0x36525853      ; 'SXR6': NP values in order
    jne dsc_5
    cmp dword ptr [esp + 0x14], 4 + 4 * NP
    jb dsc_pop
    xor edx, edx                         ; source index = target index
    jmp dsc_go
; 'SXR5' (test builds 12 / 13: Voices at 1, values from 2 one place later) and 'SXR4' (Panic last, ignored)
dsc_5:
    cmp dword ptr [eax], 0x35525853
    jne dsc_4
    cmp dword ptr [esp + 0x14], 4 + 4 * 8
    jb dsc_pop
    mov edx, 1
    jmp dsc_go
dsc_4:
    cmp dword ptr [eax], 0x34525853
    jne dsc_old0
    cmp dword ptr [esp + 0x14], 4 + 4 * 8
    jb dsc_pop
    xor edx, edx
dsc_go:
    xor ecx, ecx
dsc_loop:
    mov eax, ecx
    test ecx, ecx
    jz dsc_src
    add eax, edx
dsc_src:
    mov eax, [esi + eax * 4]
    cmp eax, [pmax + ecx * 4]
    jbe dsc_ok
    mov eax, [pdef + ecx * 4]
dsc_ok:
    mov [ivals + ecx * 4], eax
    inc ecx
    cmp ecx, NP
    jb dsc_loop
    pop esi
    jmp dsc_set
dsc_pop:
    pop esi
    jmp dsc_no
dsc_old0:
    pop esi
    mov eax, [esp + 0x14]
; 'SXR3' / 'SXR2' (old order): Reset Mode None / GM / GS / XGLite / GM2 -> GM / GS / XGLite (None, GM2 ->
; XGLite), Reverb / Chorus Return -> On if above 0, Master Volume -> 0 dB, Tune, Transpose, Polyphony kept
dsc_old:
    cmp dword ptr [eax], 0x33525853
    je dsc_o9
    cmp dword ptr [eax], 0x32525853
    jne dsc_no
    cmp dword ptr [esp + 0x10], 4 + 4 * 8
    jb dsc_no
    mov dword ptr [ivals], 248
    jmp dsc_o
dsc_o9:
    cmp dword ptr [esp + 0x10], 4 + 4 * 9
    jb dsc_no
    mov ecx, [eax + 4 + 32]
    cmp ecx, 120
    jbe dsc_p
    mov ecx, 120
dsc_p:
    mov [ivals], ecx
dsc_o:
    mov ecx, [eax + 4]
    cmp ecx, 4
    jbe dsc_r
    xor ecx, ecx
dsc_r:
    movzx ecx, byte ptr [old_mode + ecx]
    mov [ivals + 24], ecx
    xor ecx, ecx
    cmp dword ptr [eax + 4 + 20], 0
    setne cl
    mov [ivals + 4], ecx
    xor ecx, ecx
    cmp dword ptr [eax + 4 + 24], 0
    setne cl
    mov [ivals + 8], ecx
    mov dword ptr [ivals + 12], 24
    mov ecx, [eax + 4 + 12]
    cmp ecx, 200
    jbe dsc_t
    mov ecx, 100
dsc_t:
    mov [ivals + 16], ecx
    mov ecx, [eax + 4 + 16]
    cmp ecx, 48
    jbe dsc_s
    mov ecx, 24
dsc_s:
    mov [ivals + 20], ecx
dsc_set:
    mov dword ptr [ivals + 24], 3          ; Send Reset is not restored: XGLite, nothing sent
    or dword ptr [dirty], DIRTY_ALL
dsc_no:
    mov eax, 1
    ret

; append our events at edi (count ebx): the pending reset, changed master settings, Panic
emit:
    cmp dword ptr [pending], 0
    je em_par
    mov dword ptr [pending], 0
    call clr_notes
    mov eax, [ivals + 24]
    mov eax, [resets + eax * 4]            ; list: count, events (MT-32: GS reset + 26 part settings)
    mov ecx, [eax]
em_rl:
    mov edx, [eax + ecx * 4]
    mov [edi + ecx * 4 - 4], edx
    loop em_rl
    mov ecx, [eax]
    lea edi, [edi + ecx * 4]
    add ebx, ecx
    mov eax, [ivals + 24]                  ; GS mode after GS and MT-32
    xor ecx, ecx
    cmp eax, 2
    sete cl
    test eax, eax
    jnz em_gsm
    mov ecx, 1
em_gsm:
    mov [gsmode], ecx
    movzx ecx, byte ptr [lamptab + eax]    ; editor lamps: MT-32 / GS -> GS, XGLite -> XG, GM -> none, GM2 -> none (3)
    mov [lampm], ecx
    call trk_reset
    or dword ptr [dirty], DIRTY_ALL        ; a reset restores the defaults: send ours again
em_par:
    mov eax, [ivals + 4]
    imul eax, eax, 64                      ; Reverb Off / On -> return 0 / 64
    mov [sx_rev + 7], al
    mov [gs_rev + 8], al
    mov eax, [ivals + 8]
    imul eax, eax, 64
    mov [sx_cho + 7], al
    mov [gs_cho + 8], al
    mov eax, [ivals + 20]
    add eax, 0x28
    mov [sx_trn + 7], al
    mov [gs_trn + 8], al
    mov eax, [ivals + 16]
    imul eax, eax, 10
    add eax, 0x400 - 1000
    mov ecx, eax
    and ecx, 0xF
    mov [sx_tune + 10], cl
    mov [gs_tune + 11], cl
    shr eax, 4
    mov ecx, eax
    and ecx, 0xF
    mov [sx_tune + 9], cl
    mov [gs_tune + 10], cl
    shr eax, 4
    mov [sx_tune + 8], al
    mov [gs_tune + 9], al
    cmp dword ptr [gsmode], 0
    jne em_gs
    lea edx, [pev]
    jmp em_send
; GS mode: the same settings as GS system parameters (Roland checksum)
em_gs:
    mov ecx, 1
gs_ev:
    mov eax, [pev_gs + ecx * 4]
    test eax, eax
    jz gs_next
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
gs_next:
    inc ecx
    cmp ecx, NP
    jb gs_ev
    lea edx, [pev_gs]
em_send:
    mov ecx, 1
em_loop:
    bt dword ptr [dirty], ecx
    jnc em_next
    mov eax, [edx + ecx * 4]
    test eax, eax
    jz em_next
    mov [edi], eax
    add edi, 4
    inc ebx
em_next:
    inc ecx
    cmp ecx, NP
    jb em_loop
    mov dword ptr [dirty], 0
em_pq:                                     ; editor (#39): program changes / bank selects from the panel (ring of 32)
    mov ecx, [pq_tail]
    cmp ecx, [pq_head]
    je em_pq_done
    cmp ebx, 800
    jae em_pq_done
    mov eax, ecx
    and eax, 31
    mov edx, [pq + eax * 4]
    shl eax, 5
    lea eax, [pmev + eax]
    mov dword ptr [eax], 1                 ; kVstMidiType
    mov dword ptr [eax + 4], 32
    mov dword ptr [eax + 8], 0
    mov dword ptr [eax + 0xC], 0
    mov dword ptr [eax + 0x10], 0
    mov dword ptr [eax + 0x14], 0
    mov [eax + 0x18], edx
    mov dword ptr [eax + 0x1C], 0
    call trk
    mov [edi], eax
    add edi, 4
    inc ebx
    inc dword ptr [pq_tail]
    jmp em_pq
em_pq_done:
    ret

; editor (#39): program, bank MSB and LSB per channel as the plugin last sent them (host events and the panel's)
; eax = VstMidiEvent*, all registers kept
trk:
    push eax
    push ecx
    push edx
    mov edx, [eax + 0x18]
    mov ecx, edx
    and ecx, 0xF
    mov eax, edx
    and al, 0xF0
    cmp al, 0xC0
    jne tk_cc
    shr edx, 8
    and edx, 0x7F
    mov [tprg + ecx], dl
    jmp tk_ret
tk_cc:
    cmp al, 0xB0
    jne tk_ret
    mov eax, edx
    shr eax, 8
    and eax, 0x7F
    shr edx, 16
    and edx, 0x7F
    test eax, eax
    jnz tk_lsb
    mov [tmsb + ecx], dl
    jmp tk_ret
tk_lsb:
    cmp eax, 32
    jne tk_ret
    mov [tlsb + ecx], dl
tk_ret:
    pop edx
    pop ecx
    pop eax
    ret

; after a reset: program 0, banks as the mode sets them (XG: channel 10 MSB 127; GM2: 121, channel 10 120)
trk_reset:
    push eax
    push ecx
    push edx
    xor edx, edx
    cmp dword ptr [lampm], 3
    jne tr_fill
    mov edx, 121
tr_fill:
    mov ecx, 16
tr_loop:
    mov byte ptr [tprg + ecx - 1], 0
    mov byte ptr [tmsb + ecx - 1], dl
    mov byte ptr [tlsb + ecx - 1], 0
    loop tr_loop
    mov eax, [lampm]
    cmp eax, 1
    jne tr_n1
    mov byte ptr [tmsb + 9], 127
tr_n1:
    cmp eax, 3
    jne tr_ret
    mov byte ptr [tmsb + 9], 120
tr_ret:
    pop edx
    pop ecx
    pop eax
    ret

; processEvents: our events in front; resets from the host always pass
d_events:
    mov dword ptr [got], 1
    push esi
    push edi
    push ebx
    lea edi, [evlist + 8]            ; event pointer array for engine 1 (count ebx)
    xor ebx, ebx
    call clr_n                       ; and for engines 2-4 (counts nx)
    call emit
    xor ecx, ecx
    call cp_new                      ; our events go to both engines
    mov esi, [esp + 0x20]            ; host VstEvents*
    mov ecx, [esi]                   ; numEvents
    lea esi, [esi + 8]
de_loop:
    test ecx, ecx
    jz de_done
    cmp ebx, 900
    jae de_done
    mov eax, [esi]
    add esi, 4
    dec ecx
    cmp dword ptr [eax], 6           ; kVstSysExType
    jne de_keep

    mov [edi], eax
    add edi, 4
    inc ebx
    call put_all
    call is_reset                    ; a reset in the song (GM / GS / XG): send our settings again right after it
    jnz de_loop
    or dword ptr [dirty], DIRTY_ALL
    push ecx
    push esi
    mov edx, [eax + 0x18]
    xor ecx, ecx
    cmp byte ptr [edx + 1], 0x41
    sete cl
    mov [gsmode], ecx                ; GS reset: the engine now takes GS parameter SysEx only
    mov cl, [edx + 1]                ; editor lamps: Roland -> GS, Yamaha -> XG, universal (GM / GM2) -> none
    mov dword ptr [lampm], 2
    cmp cl, 0x41
    je de_lamp
    mov dword ptr [lampm], 1
    cmp cl, 0x43
    je de_lamp
    mov dword ptr [lampm], 0
    cmp byte ptr [edx + 4], 3            ; F0 7E xx 09 03: GM2 on
    jne de_lamp
    mov dword ptr [lampm], 3
de_lamp:
    call trk_reset
    push ebx
    call em_par
    pop ecx
    call cp_new
    pop esi
    pop ecx
    jmp de_loop
de_keep:
    cmp dword ptr [eax], 1           ; kVstMidiType
    jne de_one
    call trk
    call poly
    test byte ptr [route], 1
    jz de_two
    mov [edi], eax
    add edi, 4
    inc ebx
de_two:
    push ecx
    mov ecx, [route]
    call put_mask
    pop ecx
    jmp de_loop
de_one:
    mov [edi], eax
    add edi, 4
    inc ebx
    jmp de_loop
de_done:
    mov [evlist], ebx
    call send_x
    pop ebx
    pop edi
    pop esi
    lea eax, [evlist]
    mov [esp + 0x14], eax
    jmp dword ptr [orig_disp]

; ZF = 1 when the VstSysExEvent eax is a GM / GM2 / GS / XG reset
is_reset:
    push edx
    call reset_type
    test edx, edx
    jz ir_none
    cmp edx, edx
    pop edx
    ret
ir_none:
    or edx, 1
    pop edx
    ret

; reset_type: VstSysExEvent eax -> edx = 1 GM System On / GM2 On (F0 7E xx 09 01 / 03), 2 GS reset
; (F0 41 xx 42 12 40 00 7F), 3 XG System On / All Parameter Reset (F0 43 1x 4C 00 00 7E / 7F), else 0
reset_type:
    push ecx
    push esi
    mov esi, [eax + 0x18]
    mov ecx, [eax + 0x10]
    xor edx, edx
    cmp ecx, 6
    jb rt_ret
    cmp byte ptr [esi + 1], 0x7E
    jne rt_gs
    cmp byte ptr [esi + 3], 0x09
    jne rt_ret
    mov cl, [esi + 4]
    or cl, 2
    cmp cl, 3
    jne rt_ret
    mov edx, 1
    jmp rt_ret
rt_gs:
    cmp byte ptr [esi + 1], 0x41
    jne rt_xg
    cmp ecx, 8
    jb rt_ret
    cmp dword ptr [esi + 3], 0x00401242
    jne rt_ret
    cmp byte ptr [esi + 7], 0x7F
    jne rt_ret
    mov edx, 2
    jmp rt_ret
rt_xg:
    cmp byte ptr [esi + 1], 0x43
    jne rt_ret
    cmp ecx, 7
    jb rt_ret
    mov cl, [esi + 2]
    and cl, 0xF0
    cmp cl, 0x10
    jne rt_ret
    cmp word ptr [esi + 3], 0x004C
    jne rt_ret
    cmp byte ptr [esi + 5], 0
    jne rt_ret
    mov cl, [esi + 6]
    or cl, 1
    cmp cl, 0x7F
    jne rt_ret
    mov edx, 3
rt_ret:
    pop esi
    pop ecx
    ret


; copy engine 1 events from index ecx up to ebx to the other engines as well
cp_new:
    cmp ecx, ebx
    jae cn_ret
    mov eax, [evlist + 8 + ecx * 4]
    call put_all
    inc ecx
    jmp cp_new
cn_ret:
    ret

clr_n:
    push ecx
    mov ecx, NE - 1
cn_loop:
    mov dword ptr [nx + ecx * 4], 0
    loop cn_loop
    pop ecx
    ret

; add event eax to the lists of the other engines (bits 1-3 of ecx) that exist
put_all:
    push ecx
    mov ecx, 0xFE
    call put_mask
    pop ecx
    ret
put_mask:
    push edx
    push esi
    mov edx, 1
pm_loop:
    bt ecx, edx
    jnc pm_next
    cmp dword ptr [eng + edx * 4], 0
    je pm_next
    mov esi, [nx + edx * 4]
    cmp esi, 1000
    jae pm_next
    push edx
    imul edx, edx, 4096
    mov [evlx + edx + 8 + esi * 4], eax
    pop edx
    inc dword ptr [nx + edx * 4]
pm_next:
    inc edx
    cmp edx, NE
    jb pm_loop
    pop esi
    pop edx
    ret

; pass each other engine its list (processEvents); its process call applies them
send_x:
    push eax
    push ecx
    push edx
    push esi
    mov esi, 1
sx_loop:
    mov eax, [nx + esi * 4]
    test eax, eax
    jz sx_next
    cmp dword ptr [eng + esi * 4], 0
    je sx_next
    mov edx, esi
    imul edx, edx, 4096
    lea edx, [evlx + edx]
    mov [edx], eax
    push 0
    push edx
    push 0
    push 0
    push 25
    push dword ptr [eng + esi * 4]
    call dword ptr [orig_disp]
    add esp, 0x18
    mov dword ptr [evx + esi * 4], 1
    mov dword ptr [nx + esi * 4], 0
sx_next:
    inc esi
    cmp esi, NE
    jb sx_loop
    pop esi
    pop edx
    pop ecx
    pop eax
    ret

; Polyphony: sounding notes as key << 8 | channel, oldest first, and the engine that plays each (own).
; A note-on beyond the limit is dropped. Each engine has 32 voices; a new note goes to the first engine with fewer
; than 30 of our notes, else to the one with the fewest (further engines, up to 8, take the overflow). route = engine bit mask.
poly:
    push eax
    push ecx
    push edx
    push esi
    mov dword ptr [route], 0xF
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
    call own_idx
    movzx ecx, byte ptr [own + edx]
    test ecx, ecx
    jz po_lim
    mov [route], ecx                 ; a retriggered note stays on its engine and counts once
    call rm_id
    jmp po_add
po_lim:
    mov ecx, [ivals]
    add ecx, 8
    cmp [ncount], ecx
    jb po_pick
    mov dword ptr [route], 0         ; beyond the limit the new note is dropped (like the engine itself, which
    jmp po_done                      ; keeps sounding notes and gives a new note no voice when all are busy)
po_pick:
    push eax
    push esi
    push edi
    xor esi, esi                     ; engine
    xor ecx, ecx                     ; least busy so far
    mov edi, 99
pk_loop:
    cmp dword ptr [eng + esi * 4], 0
    je pk_next
    call enotes
    cmp eax, 30
    jb pk_this
    cmp eax, edi
    jae pk_next
    mov edi, eax
    mov ecx, esi
pk_next:
    inc esi
    cmp esi, NE
    jb pk_loop
    mov esi, ecx
pk_this:
    mov dword ptr [awake + esi * 4], 1
    mov dword ptr [idle + esi * 4], 0
    mov ecx, 1
    xchg ecx, esi
    shl esi, cl
    mov ecx, esi
    pop edi
    pop esi
    pop eax
po_set:
    mov [route], ecx
    call own_idx
    mov [own + edx], cl
po_add:
    mov edx, eax                     ; editor meters (#39): last accepted velocity per channel and a hit counter
    and edx, 0xF
    push eax
    mov eax, esi
    mov byte ptr [mhit + edx], al
    inc byte ptr [mseq + edx]
    pop eax
    mov ecx, [ncount]
    cmp ecx, 256
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
    cmp ecx, 64                      ; sustain pedal
    je po_sus
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
    call own_idx
    mov byte ptr [own + edx], 0
    call rm_id
    pop eax
    jmp pc_loop
pc_next:
    inc ecx
    jmp pc_loop
po_rm:
    call own_idx
    movzx ecx, byte ptr [own + edx]
    test ecx, ecx
    jz po_rm2
    mov [route], ecx
po_rm2:
    mov ecx, eax
    and ecx, 0xF
    cmp byte ptr [sus + ecx], 0
    je po_rm3
    call mark_sus                    ; pedal down: the note keeps sounding until the pedal is released
    jmp po_done
po_rm3:
    mov byte ptr [own + edx], 0
    call rm_id
    jmp po_done
; sustain pedal: down -> note-offs on the channel keep their notes (flag 0x10000); up -> those notes end
po_sus:
    and eax, 0xF
    cmp esi, 64
    jb po_sus_up
    mov byte ptr [sus + eax], 1
    jmp po_done
po_sus_up:
    mov byte ptr [sus + eax], 0
    xor ecx, ecx
ps_loop:
    cmp ecx, [ncount]
    jae po_done
    mov edx, [notes + ecx * 4]
    test edx, 0x10000
    jz ps_next
    and edx, 0xF
    cmp edx, eax
    jne ps_next
    push eax
    mov eax, [notes + ecx * 4]
    call own_idx
    mov byte ptr [own + edx], 0
    call rm_id
    pop eax
    jmp ps_loop
ps_next:
    inc ecx
    jmp ps_loop
po_done:
    pop esi
    pop edx
    pop ecx
    pop eax
    ret

; edx = index of note eax (key << 8 | channel) in own: channel * 128 + key
own_idx:
    mov edx, eax
    shr edx, 8
    and edx, 0x7F
    push eax
    and eax, 0xF
    shl eax, 7
    or edx, eax
    pop eax
    ret

; forget all notes (reset, Panic)
clr_notes:
    push ecx
    mov dword ptr [ncount], 0
    mov dword ptr [sus], 0
    mov dword ptr [sus + 4], 0
    mov dword ptr [sus + 8], 0
    mov dword ptr [sus + 12], 0
    mov ecx, 512
cl_loop:
    mov dword ptr [own + ecx * 4 - 4], 0
    loop cl_loop
    pop ecx
    ret

; eax = number of sounding notes routed to engine esi (from our own note list). The engine's voice manager is
; not read: its place in the plugin object depends on the CPU (the engine picks its code path at run time; the
; emulator without SSE and a real CPU differ), so reading it crashed on real machines.
enotes:
    push ebx
    push ecx
    push edx
    xor ebx, ebx
    xor ecx, ecx
en_loop:
    cmp ecx, [ncount]
    jae en_ret
    mov eax, [notes + ecx * 4]
    call own_idx
    movzx eax, byte ptr [own + edx]
    bt eax, esi
    jnc en_next
    inc ebx
en_next:
    inc ecx
    jmp en_loop
en_ret:
    mov eax, ebx
    pop edx
    pop ecx
    pop ebx
    ret

; remove note eax from the list
rm_id:
    push ecx
    push edx
    push ebx
    mov ebx, eax
    and ebx, 0xFFFF
    xor ecx, ecx
ri_find:
    cmp ecx, [ncount]
    jae ri_ret
    mov edx, [notes + ecx * 4]
    and edx, 0xFFFF
    cmp edx, ebx
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
    pop ebx
    pop edx
    pop ecx
    ret
; mark_sus: note eax (key << 8 | channel) is held by the pedal (flag 0x10000)
mark_sus:
    push ecx
    push edx
    xor ecx, ecx
ms_find:
    cmp ecx, [ncount]
    jae ms_ret
    mov edx, [notes + ecx * 4]
    and edx, 0xFFFF
    cmp edx, eax
    je ms_set
    inc ecx
    jmp ms_find
ms_set:
    or dword ptr [notes + ecx * 4], 0x10000
ms_ret:
    pop edx
    pop ecx
    ret

; at mains on create the engines Polyphony needs (32 voices each, up to 8); the first mains on also makes
; the original main() once more
; (our hook stays out of it), then open / sample rate / block size like the host did for engine 1
mkx:

    push esi
    push edi
    mov edi, [ivals]
    add edi, 8 + 31
    shr edi, 5                       ; engines needed
    mov esi, 1
mk_loop:
    cmp esi, edi
    jae mk_ret
    cmp dword ptr [eng + esi * 4], 0
    jne mk_next
    mov eax, [eng]
    push dword ptr [eax - 0x14]      ; audioMaster
    mov dword ptr [creating], 1
    lea eax, [IMG + 0x2c80]
    call eax
    add esp, 4
    mov dword ptr [creating], 0
    test eax, eax
    jz mk_ret
    push esi
    mov esi, eax
    push 0
    push 0
    push 0
    push 0
    push 0                           ; effOpen
    push esi
    call dword ptr [orig_disp]
    add esp, 0x18
    push dword ptr [srv]
    push 0
    push 0
    push 0
    push 10                          ; effSetSampleRate
    push esi
    call dword ptr [orig_disp]
    add esp, 0x18
    push 0
    push 0
    push dword ptr [bsv]
    push 0
    push 11                          ; effSetBlockSize
    push esi
    call dword ptr [orig_disp]
    add esp, 0x18
    mov eax, esi
    pop esi
    mov [eng + esi * 4], eax
mk_next:
    inc esi
    jmp mk_loop
mk_ret:
    pop edi
    pop esi
    ret

; process / processReplacing: send our pending events when the host sent none this block, render
; engine 1, then engine 2 while it is awake (added to the output); it falls asleep 192000 samples
; after its last voice ended (release and effect tails), and only takes events (0-sample process) then
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
    call clr_n
    call emit
    mov [evlist], ebx
    xor ecx, ecx
    call cp_new
    call send_x
    mov eax, ebx
    pop ebx
    pop edi
    test eax, eax
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
    push dword ptr [esp + 0x10]
    push dword ptr [esp + 0x10]
    push dword ptr [esp + 0x10]
    push dword ptr [esp + 0x10]
    call dword ptr [p_target]
    add esp, 0x10
    push esi
    mov esi, 1
px_loop:
    cmp dword ptr [eng + esi * 4], 0
    je px_next
    cmp dword ptr [awake + esi * 4], 0
    jne px_run
    cmp dword ptr [evx + esi * 4], 0
    je px_next
    mov dword ptr [evx + esi * 4], 0
    push 0                           ; asleep: 0 samples, only its events
    lea eax, [tptrs]
    push eax
    push eax
    push dword ptr [eng + esi * 4]
    call dword ptr [orig_repl]
    add esp, 0x10
    jmp px_next
px_run:
    call run_eng
px_next:
    inc esi
    cmp esi, NE
    jb px_loop
    pop esi
    cmp dword ptr [ivals + 12], 24        ; Master Volume (output gain), processReplacing only
    je px_ret
    mov eax, [orig_repl]
    cmp [p_target], eax
    jne px_ret
    mov eax, [ivals + 12]
    fld dword ptr [gains + eax * 4]
    mov edx, [esp + 0xC]                  ; outputs
    mov ecx, [esp + 0x10]                 ; frames
    push esi
    mov eax, [edx]
    mov edx, [edx + 4]
    xor esi, esi
pg_loop:
    cmp esi, ecx
    jae pg_done
    fld dword ptr [eax + esi * 4]
    fmul st(0), st(1)
    fstp dword ptr [eax + esi * 4]
    fld dword ptr [edx + esi * 4]
    fmul st(0), st(1)
    fstp dword ptr [edx + esi * 4]
    inc esi
    jmp pg_loop
pg_done:
    pop esi
    fstp st(0)
px_ret:
    push dword ptr [esp + 0x10]           ; editor (#39): peak of the outputs for the L / R meters
    push dword ptr [esp + 0x10]
    lea eax, [ed_blob + 32]
    call eax
    add esp, 8
    ret

; render engine esi (awake) in pieces of 512 samples and add it to the outputs
run_eng:
    mov dword ptr [evx + esi * 4], 0
    push edi
    push ebx
    push ebp
    mov ebp, [esp + 0x24]            ; frames left
    xor ebx, ebx                     ; frames done
pr_loop:
    test ebp, ebp
    jle pr_done
    mov ecx, ebp
    cmp ecx, 512
    jbe pr_n
    mov ecx, 512
pr_n:
    push ecx
    push ecx
    lea eax, [tptrs]
    push eax
    push eax
    push dword ptr [eng + esi * 4]
    call dword ptr [orig_repl]
    add esp, 0x10
    pop ecx
    mov edx, [esp + 0x20]            ; outputs
    mov eax, [edx]
    lea eax, [eax + ebx * 4]
    mov edi, [edx + 4]
    lea edi, [edi + ebx * 4]
    push ecx
    xor edx, edx
pr_add:
    fld dword ptr [tbuf0 + edx * 4]
    fadd dword ptr [eax + edx * 4]
    fstp dword ptr [eax + edx * 4]
    fld dword ptr [tbuf1 + edx * 4]
    fadd dword ptr [edi + edx * 4]
    fstp dword ptr [edi + edx * 4]
    inc edx
    cmp edx, ecx
    jb pr_add
    pop ecx
    add ebx, ecx
    sub ebp, ecx
    jmp pr_loop
pr_done:
    call enotes
    test eax, eax
    jnz pr_busy
    mov eax, [esp + 0x24]
    add [idle + esi * 4], eax
    cmp dword ptr [idle + esi * 4], 192000
    jb pr_out
    mov dword ptr [awake + esi * 4], 0
    jmp pr_out
pr_busy:
    mov dword ptr [idle + esi * 4], 0
pr_out:
    pop ebp
    pop ebx
    pop edi
    ret

.align 4
names: .int s_poly, s_rev, s_cho, s_vol, s_tune, s_trn, s_reset
labels: .int s_empty, s_empty, s_empty, s_db, s_cent, s_semi, s_empty
pmax: .int 248, 1, 1, 48, 200, 48, 4
pdef: .int 248, 1, 1, 24, 100, 24, 3
poff: .int -8, 0, 0, 0, 100, 24, 0
pflag: .int 0xE, 0xF, 0xF, 0xE, 0xE, 0xE, 0xE   ; IsSwitch 1, IntMinMax 2, FloatStep 4, IntStep 8
etab: .int 0, offon, offon, voltxt, 0, 0, modes
pev: .int 0, ev_rev, ev_cho, 0, ev_tune, ev_trn, 0
pev_gs: .int 0, eg_rev, eg_cho, 0, eg_tune, eg_trn, 0
modes: .int s_mt, s_gm, s_gs, s_xgl, s_gm2
old_mode: .byte 3, 1, 2, 3, 3, 0, 0, 0
offon: .int s_off, s_on
resets: .int rl_mt, rl_gm, rl_gs, rl_xg, rl_gm2
rl_gm: .int 1, ev_gm
rl_gs: .int 1, ev_gs
rl_xg: .int 1, ev_xg
rl_gm2: .int 1, ev_gm2
MTTABLES
VOLTABLES
s_reset: .asciz "Send Reset"
s_kernel: .asciz "KERNEL32.dll"
s_find: .asciz "FindResourceA"
s_load: .asciz "LoadResource"
s_size: .asciz "SizeofResource"
s_vol: .asciz "Master Volume"
s_tune: .asciz "Master Tune"
s_trn: .asciz "Transpose"
s_rev: .asciz "Reverb (CC 91)"
s_cho: .asciz "Chorus (CC 93)"
s_db: .asciz "dB"
s_poly: .asciz "Polyphony"
s_cent: .asciz "cent"
s_semi: .asciz "semi"
s_empty: .byte 0
s_gm: .asciz "GM"
s_gs: .asciz "GS"
s_xgl: .asciz "XGLite"
s_gm2: .asciz "GM2"
s_mt: .asciz "MT-32"
s_on: .asciz "On"
s_off: .asciz "Off"
.align 4
; VstSysExEvent: type 6, byteSize 32, deltaFrames, flags, dumpBytes, resvd1, sysexDump*, resvd2
ev_gm: .int 6, 32, 0, 0, 6, 0, sx_gm, 0
ev_gm2: .int 6, 32, 0, 0, 6, 0, sx_gm2, 0
ev_gs: .int 6, 32, 0, 0, 11, 0, sx_gs, 0
ev_xg: .int 6, 32, 0, 0, 9, 0, sx_xg, 0
ev_tune: .int 6, 32, 0, 0, 12, 0, sx_tune, 0
ev_trn: .int 6, 32, 0, 0, 9, 0, sx_trn, 0
ev_rev: .int 6, 32, 0, 0, 9, 0, sx_rev, 0
ev_cho: .int 6, 32, 0, 0, 9, 0, sx_cho, 0
eg_tune: .int 6, 32, 0, 0, 14, 0, gs_tune, 0
eg_trn: .int 6, 32, 0, 0, 11, 0, gs_trn, 0
eg_rev: .int 6, 32, 0, 0, 11, 0, gs_rev, 0
eg_cho: .int 6, 32, 0, 0, 11, 0, gs_cho, 0
sx_gm: .byte 0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7
sx_gm2: .byte 0xF0, 0x7E, 0x7F, 0x09, 0x03, 0xF7
sx_gs: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41, 0xF7
sx_xg: .byte 0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00, 0xF7
sx_tune: .byte 0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0xF7
sx_trn: .byte 0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x06, 0x40, 0xF7
sx_rev: .byte 0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x0C, 0x40, 0xF7
sx_cho: .byte 0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x2C, 0x40, 0xF7
gs_tune: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0xF7
gs_trn: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x05, 0x40, 0x00, 0xF7
gs_rev: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x01, 0x33, 0x40, 0x00, 0xF7
gs_cho: .byte 0xF0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x01, 0x3A, 0x40, 0x00, 0xF7
.align 4
ivals: .int 248, 1, 1, 24, 100, 24, 3     ; = pdef
pending: .int 0
started: .int 0
dirty: .int 0
gsmode: .int 0
lampm: .int 1                         ; editor lamps / bank display: 0 GM, 1 XG (start: XGLite), 2 GS, 3 GM2
lamptab: .byte 2, 0, 2, 1, 3
.align 4
ed_share: .int ncount, notes, mhit, mseq, lampm, ivals, tprg, tmsb, tlsb, pq, pq_head, pq_tail
mhit: .space 16
mseq: .space 16
tprg: .space 16
tmsb: .byte 0, 0, 0, 0, 0, 0, 0, 0, 0, 127, 0, 0, 0, 0, 0, 0
tlsb: .space 16
pq_head: .int 0
pq_tail: .int 0
pq: .space 4 * 32
pmev: .space 32 * 32
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
sus: .space 16
notes: .space 4 * 256
own: .space 16 * 128
route: .int 0
eng: .int 0, 0, 0, 0, 0, 0, 0, 0
creating: .int 0
awake: .int 0, 0, 0, 0, 0, 0, 0, 0
idle: .int 0, 0, 0, 0, 0, 0, 0, 0
evx: .int 0, 0, 0, 0, 0, 0, 0, 0
nx: .int 0, 0, 0, 0, 0, 0, 0, 0
srv: .float 44100.0
bsv: .int 1024
tptrs: .int tbuf0, tbuf1
tbuf0: .space 4 * 512
tbuf1: .space 4 * 512
evlx: .space 8 * 4096
chunk: .int 0x36525853
.space 4 * NP
evlist: .int 0, 0
.space 4096
str_name: .ascii "S-YXG2006LE"
.byte 0
str_vendor: .ascii "Yamaha"
.byte 0
str_product: .ascii "Yamaha S-YXG2006LE"
.byte 0
.align 64                             ; ld aligns the blob to its largest input alignment (checked by mksgp2.py)
ed_blob:
