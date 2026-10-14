; GUI additions, syxg50.dll: the reset modes of the Settings page (dialog 111, "Utility" box, page code in
; settings.asm) and the audio-thread side of the panel controls (pending reset, held events, program step).
; Code cave at 0x10033150 (unused NOP block inside .text, no relocations), position independent
; (call/pop, ebp = load delta). State in .data:
;   0x10056E40  pending reset (0 = none, 1 = GM, 2 = GS, 3 = XG, 6 = none, only filter this block), set by the
;               Settings page, the plugin state, the first block or song_check, taken by the audio thread
;   0x10056E41  Reset Mode (1 = GM, 2 = GS, 3 = XG) XOR 3, so the zeroed .data means XG (default)
;   0x10056E42  pending program step (signed), added by the panel buttons / mouse wheel, taken by the audio thread
;   0x10056E43  preset button held (0 = none, 1 = down, 2 = up)
;   0x10056E44  engine (plugin +0xB0), stored by the audio thread for the readout (0 until audio runs)
;   0x10056E48  SetTimer, 0x10056E4C KillTimer (user32, looked up on the first button press)
;   0x10056E50  mouse wheel remainder (WHEEL_DELTA = 120 per step)
;   0x10056E54  samples left until host events may pass again after a reset (4800 = 100 ms at 48 kHz)
;   0x10056E58  event queue (VirtualAlloc 64 KB on the first reset): VstEvents header + 256 pointers at +0,
;               256 events of 32 bytes at +1032, SysEx bytes (32 KB) at +9224
;   0x10056E5C  queued events, 0x10056E60 queued SysEx bytes
;   0x10056E64  Reset Mode sent once after loading (0 = not yet: the first block sends it)
; The Reset Mode is sent once: in the first block, when it is picked on the Settings page and when the host
; restores the plugin state. Resets from the host (MIDI file or player) follow the mode (reset_drop):
; XG: all pass. GS: GM System On / GM2 On is replaced by the GS reset, GS and XG pass. GM: GS and XG resets
; are dropped, GM passes.
; Events go through the same entries as host events (engine vtable +0x0C SysEx (engine, data, length),
; +0x08 short message (engine, packed bytes), stdcall), at the start of the next process call. Host events
; that arrive while a reset settles are held back with deltaFrames 0 and passed on in the first block after it.
; The panel controls (channel, program / bank select) are in dev/poly/panel.asm (section .sxp); send_pending
; calls its panel_prog for the pending program / bank step.

; --- send_pending: called by the process / processReplacing wrappers (poly.asm) before the block is rendered
; after pushal: effect [esp+0x28], sampleFrames [esp+0x34]
send_pending:
    pushal
    call sp_base
sp_base:
    pop ebp
    sub ebp, sp_base
    mov edx, dword ptr [esp + 0x28]
    mov esi, dword ptr [edx + 0x40]
    mov ecx, dword ptr [esi + 0xb0]
    mov dword ptr [ebp + 0x10056e44], ecx
    test ecx, ecx
    je sp_done
    cmp byte ptr [ebp + 0x10056e64], 0
    jne sp_check
    mov byte ptr [ebp + 0x10056e64], 1
    call mark_pending
sp_check:
    call song_check
    mov ecx, dword ptr [ebp + 0x10056e44]
    xor eax, eax
    xchg byte ptr [ebp + 0x10056e40], al
    test eax, eax
    je sp_queue
    cmp eax, 6
    je sp_filter
    cmp eax, 2
    je sp_gs
    ja sp_xg
    lea edi, [ebp + gm_reset]
    push 6
    jmp sp_send
sp_gs:
    lea edi, [ebp + gs_reset]
    push 11
    jmp sp_send
sp_xg:
    lea edi, [ebp + xg_reset]
    push 9
sp_send:
    push edi
    call BOTH_SYSEX
sp_hold:
    mov dword ptr [ebp + 0x10056e54], 4800
    jmp sp_queue
; only a dropped reset: this block's events go through the queue (filtered) and pass at once
sp_filter:
    cmp dword ptr [ebp + 0x10056e54], 0
    jne sp_queue
    mov dword ptr [ebp + 0x10056e54], 1
sp_queue:
    mov eax, dword ptr [ebp + 0x10056e54]
    or eax, dword ptr [ebp + 0x10056e5c]
    je sp_prog
    mov edi, dword ptr [ebp + 0x10056e58]
    test edi, edi
    je sp_prog
    mov ebx, dword ptr [esi + 0xe0]
    test ebx, ebx
    je sp_held
    mov ecx, dword ptr [ebx]
    xor edx, edx
sp_qloop:
    cmp edx, ecx
    jge sp_held
    push ecx
    push edx
    mov eax, dword ptr [ebx + edx*4 + 8]
    call q_add
    pop edx
    pop ecx
    inc edx
    jmp sp_qloop
sp_held:
    mov dword ptr [esi + 0xe0], 0
    mov eax, dword ptr [esp + 0x34]
    sub dword ptr [ebp + 0x10056e54], eax
    jg sp_done
    mov dword ptr [ebp + 0x10056e54], 0
    mov ecx, dword ptr [ebp + 0x10056e5c]
    test ecx, ecx
    je sp_prog
    mov dword ptr [edi], ecx
    mov dword ptr [ebp + 0x10056e5c], 0
    mov dword ptr [ebp + 0x10056e60], 0
    mov dword ptr [esi + 0xe0], edi
sp_prog:
    call PANEL_PROG
sp_done:
    popal
    ret
; song_check (esi = plugin): reset SysEx among the host events of this block -> reset_drop decides;
; a dropped reset makes this block go through the queue (pending 6, unless a reset is pending anyway),
; a GM reset in GS mode makes the GS reset pending
song_check:
    mov ebx, dword ptr [esi + 0xe0]
    test ebx, ebx
    je sc_end
    xor edx, edx
sf_loop:
    cmp edx, dword ptr [ebx]
    jge sc_end
    mov edi, dword ptr [ebx + edx*4 + 8]
    cmp dword ptr [edi], 6
    jne sf_next
    push edx
    mov ecx, dword ptr [edi + 0x10]
    mov eax, dword ptr [edi + 0x18]
    call reset_drop
    test eax, eax
    je sf_pop
    cmp eax, 2
    je sf_gs
    cmp byte ptr [ebp + 0x10056e40], 0
    jne sf_pop
    mov al, 6
sf_gs:
    call set_pending
sf_pop:
    pop edx
sf_next:
    inc edx
    jmp sf_loop
sc_end:
    ret
; mark_pending: the Reset Mode becomes the pending reset
mark_pending:
    movzx eax, byte ptr [ebp + 0x10056e41]
    xor al, 3
    jne set_pending
    mov al, 3
; set_pending: al = pending reset; allocates the event queue on first use
set_pending:
    mov byte ptr [ebp + 0x10056e40], al
    cmp dword ptr [ebp + 0x10056e58], 0
    jne mp_ret
    push 4
    push 0x3000
    push 0x10000
    push 0
    call dword ptr [ebp + 0x1004013c]
    mov dword ptr [ebp + 0x10056e58], eax
mp_ret:
    ret
; reset_drop: eax = SysEx data, ecx = length -> eax = 0 pass, 1 drop, 2 drop and send the GS reset
reset_drop:
    call is_reset
    movzx ecx, byte ptr [ebp + 0x10056e41]
    xor cl, 3
    cmp cl, 2
    ja rd_pass
    je rd_gs
    cmp eax, 2
    jb rd_pass
    mov eax, 1
    ret
rd_gs:
    cmp eax, 1
    jne rd_pass
    mov eax, 2
    ret
rd_pass:
    xor eax, eax
    ret
; is_reset: eax = SysEx data, ecx = length -> eax = 1 for GM System On / GM2 On (F0 7E xx 09 01 / 03),
; 2 for GS reset / system mode set (F0 41 xx 42 12 40 00 7F ..), 3 for XG System On / All Parameter Reset
; (F0 43 1x 4C 00 00 7E / 7F ..), else 0
is_reset:
    push edx
    mov edx, eax
    xor eax, eax
    cmp ecx, 5
    jb ir_out
    cmp byte ptr [edx], 0xf0
    jne ir_out
    cmp byte ptr [edx + 1], 0x7e
    jne ir_gs
    cmp byte ptr [edx + 3], 9
    jne ir_out
    mov cl, byte ptr [edx + 4]
    or cl, 2
    cmp cl, 3
    jne ir_out
    mov eax, 1
    jmp ir_out
ir_gs:
    cmp ecx, 8
    jb ir_out
    cmp byte ptr [edx + 1], 0x41
    jne ir_xg
    cmp dword ptr [edx + 3], 0x00401242
    jne ir_out
    cmp byte ptr [edx + 7], 0x7f
    jne ir_out
    mov eax, 2
    jmp ir_out
ir_xg:
    cmp byte ptr [edx + 1], 0x43
    jne ir_out
    mov cl, byte ptr [edx + 2]
    and cl, 0xf0
    cmp cl, 0x10
    jne ir_out
    cmp dword ptr [edx + 3], 0x7e00004c
    je ir_yes
    cmp dword ptr [edx + 3], 0x7f00004c
    jne ir_out
ir_yes:
    mov eax, 3
ir_out:
    pop edx
    ret
; q_add: copy host event eax into the queue (edi), deltaFrames 0; SysEx data copied too. Full queue: dropped.
; A reset SysEx that reset_drop drops is left out.
q_add:
    cmp dword ptr [eax], 6
    jne q_go
    push eax
    push ecx
    push edx
    mov ecx, dword ptr [eax + 0x10]
    mov eax, dword ptr [eax + 0x18]
    call reset_drop
    test eax, eax
    pop edx
    pop ecx
    pop eax
    jne q_ret
q_go:
    mov edx, dword ptr [ebp + 0x10056e5c]
    cmp edx, 256
    jae q_ret
    push esi
    mov esi, eax
    imul ecx, edx, 32
    lea ecx, [edi + ecx + 1032]
    mov dword ptr [edi + edx*4 + 8], ecx
    push edi
    push ecx
    mov edi, ecx
    mov ecx, 32
    rep movsb
    pop ecx
    pop edi
    mov dword ptr [ecx + 8], 0
    cmp dword ptr [ecx], 6
    jne q_ok
    mov eax, dword ptr [ecx + 0x10]
    mov edx, dword ptr [ebp + 0x10056e60]
    lea esi, [edx + eax]
    cmp esi, 32768
    ja q_drop
    mov dword ptr [ebp + 0x10056e60], esi
    lea edx, [edi + edx + 9224]
    mov esi, dword ptr [ecx + 0x18]
    mov dword ptr [ecx + 0x18], edx
    push edi
    push ecx
    mov edi, edx
    mov ecx, eax
    rep movsb
    pop ecx
    pop edi
q_ok:
    inc dword ptr [ebp + 0x10056e5c]
q_drop:
    pop esi
q_ret:
    ret

gm_reset:
    .byte 0xf0, 0x7e, 0x7f, 0x09, 0x01, 0xf7
gs_reset:
    .byte 0xf0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7f, 0x00, 0x41, 0xf7
xg_reset:
    .byte 0xf0, 0x43, 0x10, 0x4c, 0x00, 0x00, 0x7e, 0x00, 0xf7
