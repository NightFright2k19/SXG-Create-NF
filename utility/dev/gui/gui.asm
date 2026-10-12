; GUI additions, syxg50.dll: the reset modes of the Settings page (dialog 111, "Utility" box, page code in
; settings.asm) and the preset buttons in the panel (program down / up on MIDI channel 1 with a 3-digit readout).
; Code cave at 0x10033150 (unused NOP block inside .text, no relocations), position independent
; (call/pop, ebp = load delta). State in .data:
;   0x10056E40  pending reset (0 = none, 1 = GM, 2 = GS, 3 = XG, 5 = None: controller resets only), set by the
;               Settings page or by a new song (see song_check), taken by the audio thread
;   0x10056E41  Reset Mode (0 = None, 1 = GM, 2 = GS, 3 = XG) XOR 3, so the zeroed .data means XG (default)
;   0x10056E42  pending program step (signed), added by the panel buttons / mouse wheel, taken by the audio thread
;   0x10056E43  preset button held (0 = none, 1 = down, 2 = up)
;   0x10056E44  engine (plugin +0xB0), stored by the audio thread for the readout (0 until audio runs)
;   0x10056E48  SetTimer, 0x10056E4C KillTimer (user32, looked up on the first button press)
;   0x10056E50  mouse wheel remainder (WHEEL_DELTA = 120 per step)
;   0x10056E54  samples left until host events may pass again after a reset (4800 = 100 ms at 48 kHz)
;   0x10056E58  event queue (VirtualAlloc 64 KB on the first reset): VstEvents header + 256 pointers at +0,
;               256 events of 32 bytes at +1032, SysEx bytes (32 KB) at +9224
;   0x10056E5C  queued events, 0x10056E60 queued SysEx bytes
;   0x10056E64  "Enable SysEx in files" (0 = off, default: resets from the host are replaced by the Reset Mode)
;   0x10056E65  host transport was playing in the last block (getTimeInfo flags bit 1)
;   0x10056E68  EnableWindow (user32, looked up by the Settings page)
; New song (only while "Enable SysEx in files" is off): the host transport starts playing, or a GM / GS / XG
; reset SysEx arrives from the host (MIDI file or player). The Reset Mode is then sent instead (None: All Sound
; Off, All Notes Off, Reset All Controllers on all 16 channels), the host's reset is dropped.
; Events go through the same entries as host events (engine vtable +0x0C SysEx (engine, data, length),
; +0x08 short message (engine, packed bytes), stdcall), at the start of the next process call. Host events
; that arrive while a reset settles are held back with deltaFrames 0 and passed on in the first block after it.
; Panel (bitmap 101, title strip): buttons 15 x 15 at (164,4) and (221,4), readout digits (bitmap 105,
; 10 x 13) at (185,5), pressed buttons in bitmap 106 at (160,0) and (175,0). Holding a button repeats the
; step (first after 400 ms, then every 75 ms, panel timer 0x2317); the wheel over the control steps up / down.
; The program of part 1 is byte +0x366 of the synth object [engine +8] (0-127, shown as 001-128).

; --- process / processReplacing wrappers (0x100010A0 / 0x100010C0) jump here
proc_hook:
    call send_pending
    mov eax, dword ptr [esp + 4]
    mov ecx, dword ptr [eax + 0x40]
    jmp 0x100010c7
procacc_hook:
    call send_pending
    mov eax, dword ptr [esp + 4]
    mov ecx, dword ptr [eax + 0x40]
    jmp 0x100010a7
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
    jne sp_take
    call song_check
sp_take:
    mov ecx, dword ptr [ebp + 0x10056e44]
    xor eax, eax
    xchg byte ptr [ebp + 0x10056e40], al
    test eax, eax
    je sp_queue
    cmp eax, 5
    je sp_none
    cmp eax, 2
    je sp_gs
    jb sp_gm
    cmp eax, 4
    jne sp_xg
    lea edi, [ebp + gm2_reset]
    push 6
    jmp sp_send
sp_gm:
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
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 0xc]
    jmp sp_hold
sp_none:
    xor ebx, ebx
sn_loop:
    lea eax, [ebx + 0x78b0]
    call sn_cc
    lea eax, [ebx + 0x7bb0]
    call sn_cc
    lea eax, [ebx + 0x79b0]
    call sn_cc
    inc ebx
    cmp ebx, 16
    jb sn_loop
sp_hold:
    mov dword ptr [ebp + 0x10056e54], 4800
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
    mov ecx, dword ptr [ebp + 0x10056e44]
    xor eax, eax
    xchg byte ptr [ebp + 0x10056e42], al
    test al, al
    je sp_done
    movsx eax, al
    mov edx, dword ptr [ecx + 8]
    movzx edx, byte ptr [edx + 0x366]
    add eax, edx
    and eax, 0x7f
    shl eax, 8
    or eax, 0xc0
    push eax
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 8]
sp_done:
    popal
    ret
; sn_cc: short message eax (status | data1 << 8 | data2 << 16) to the engine
sn_cc:
    mov ecx, dword ptr [ebp + 0x10056e44]
    push eax
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 8]
    ret
; song_check (esi = plugin, effect at [esp+0x2c]): transport start (audioMaster at plugin +0x0C,
; getTimeInfo = opcode 7) or a reset SysEx among the host events of this block -> Reset Mode pending
song_check:
    mov eax, dword ptr [esi + 0xc]
    test eax, eax
    je sc_filter
    push 0
    push 0
    push 0
    push 0
    push 7
    push dword ptr [esp + 0x40]
    call eax
    add esp, 24
    xor ecx, ecx
    test eax, eax
    je sc_state
    mov ecx, dword ptr [eax + 84]
    shr ecx, 1
    and ecx, 1
sc_state:
    mov al, byte ptr [ebp + 0x10056e65]
    mov byte ptr [ebp + 0x10056e65], cl
    test cl, cl
    je sc_filter
    test al, al
    jne sc_filter
    call mark_pending
sc_filter:
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
    call is_reset
    test eax, eax
    je sf_pop
    call mark_pending
sf_pop:
    pop edx
sf_next:
    inc edx
    jmp sf_loop
sc_end:
    ret
; mark_pending: the Reset Mode becomes the pending reset; allocates the event queue on first use
mark_pending:
    movzx eax, byte ptr [ebp + 0x10056e41]
    xor al, 3
    jne mp_set
    mov al, 5
mp_set:
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
; is_reset: eax = SysEx data, ecx = length -> eax = 1 for GM System On / Off / GM2 On (F0 7E xx 09 ..),
; GS reset / system mode set (F0 41 xx 42 12 40 00 7F ..), XG System On / All Parameter Reset
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
    jmp ir_yes
ir_gs:
    cmp ecx, 8
    jb ir_out
    cmp byte ptr [edx + 1], 0x41
    jne ir_xg
    cmp dword ptr [edx + 3], 0x00401242
    jne ir_out
    cmp byte ptr [edx + 7], 0x7f
    jne ir_out
    jmp ir_yes
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
    mov eax, 1
ir_out:
    pop edx
    ret
; q_add: copy host event eax into the queue (edi), deltaFrames 0; SysEx data copied too. Full queue: dropped.
; A reset SysEx is dropped while "Enable SysEx in files" is off (the Reset Mode was sent instead).
q_add:
    cmp dword ptr [eax], 6
    jne q_go
    cmp byte ptr [ebp + 0x10056e64], 0
    jne q_go
    push eax
    push ecx
    push edx
    mov ecx, dword ptr [eax + 0x10]
    mov eax, dword ptr [eax + 0x18]
    call is_reset
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

; --- panel window (0x10032260, (this, hwnd, msg, wparam, lparam), locals 0x40 + 4 pushes: hwnd [esp+0x58],
;     wparam [esp+0x60], lparam [esp+0x64]); WM_LBUTTONDOWN (0x1003246B), WM_LBUTTONUP (0x10032427) and the
;     DefWindowProc branch (0x10032407: WM_TIMER, WM_MOUSEWHEEL) jump here
lbd_hook:
    mov eax, dword ptr [esp + 0x64]
    movsx ecx, ax
    sar eax, 16
    cmp eax, 4
    jl lbd_orig
    cmp eax, 19
    jge lbd_orig
    mov edx, 1
    cmp ecx, 164
    jl lbd_orig
    cmp ecx, 179
    jl lbd_hit
    mov edx, 2
    cmp ecx, 221
    jl lbd_orig
    cmp ecx, 236
    jge lbd_orig
lbd_hit:
    pushal
    call lbd_base
lbd_base:
    pop ebp
    sub ebp, lbd_base
    mov byte ptr [ebp + 0x10056e43], dl
    mov al, 1
    cmp dl, 1
    jne lbd_up
    neg al
lbd_up:
    lock add byte ptr [ebp + 0x10056e42], al
    mov ebx, dword ptr [esp + 0x78]
    push ebx
    call dword ptr [ebp + 0x100401a4]
    push ebx
    call draw_buttons
    call get_timers
    test eax, eax
    je lbd_end
    push 0
    push 400
    push 0x2317
    push ebx
    call eax
lbd_end:
    popal
    jmp 0x100324b3
lbd_orig:
    mov esi, dword ptr [esp + 0x54]
    mov al, byte ptr [esi + 0x8c]
    jmp 0x10032475

lbu_hook:
    pushal
    call lbu_base
lbu_base:
    pop ebp
    sub ebp, lbu_base
    cmp byte ptr [ebp + 0x10056e43], 0
    je lbu_none
    mov byte ptr [ebp + 0x10056e43], 0
    call dword ptr [ebp + 0x100401a0]
    mov eax, dword ptr [ebp + 0x10056e4c]
    test eax, eax
    je lbu_draw
    push 0x2317
    push dword ptr [esp + 0x7c]
    call eax
lbu_draw:
    push dword ptr [esp + 0x78]
    call draw_buttons
    popal
    jmp 0x100324b3
lbu_none:
    popal
    mov esi, dword ptr [esp + 0x54]
    mov al, byte ptr [esi + 0x8c]
    jmp 0x10032431

def_hook:
    cmp eax, 0x113
    je dh_timer
    cmp eax, 0x20a
    je dh_wheel
dh_orig:
    mov ecx, dword ptr [esp + 0x64]
    mov edx, dword ptr [esp + 0x60]
    jmp 0x1003240f
dh_timer:
    cmp dword ptr [esp + 0x60], 0x2317
    jne dh_orig
    pushal
    call dt_base
dt_base:
    pop ebp
    sub ebp, dt_base
    mov ebx, dword ptr [esp + 0x78]
    movzx edx, byte ptr [ebp + 0x10056e43]
    test edx, edx
    je dt_kill
    mov al, 1
    cmp dl, 1
    jne dt_up
    neg al
dt_up:
    lock add byte ptr [ebp + 0x10056e42], al
    push 0
    push 75
    push 0x2317
    push ebx
    call dword ptr [ebp + 0x10056e48]
    jmp dh_done
dt_kill:
    push 0x2317
    push ebx
    call dword ptr [ebp + 0x10056e4c]
dh_done:
    popal
    jmp 0x100324b3
; wheel: lparam = screen position, high word of wparam = delta; panel has no border (window = client)
dh_wheel:
    pushal
    call dw_base
dw_base:
    pop ebp
    sub ebp, dw_base
    sub esp, 16
    push esp
    push dword ptr [esp + 0x8c]
    call dword ptr [ebp + 0x100401bc]
    movsx ecx, word ptr [esp + 0x94]
    movsx edx, word ptr [esp + 0x96]
    sub ecx, dword ptr [esp]
    sub edx, dword ptr [esp + 4]
    add esp, 16
    cmp ecx, 164
    jl dw_out
    cmp ecx, 236
    jge dw_out
    cmp edx, 4
    jl dw_out
    cmp edx, 19
    jge dw_out
    movsx eax, word ptr [esp + 0x82]
    add eax, dword ptr [ebp + 0x10056e50]
    cdq
    mov ecx, 120
    idiv ecx
    mov dword ptr [ebp + 0x10056e50], edx
    lock add byte ptr [ebp + 0x10056e42], al
    popal
    jmp 0x100324b3
dw_out:
    popal
    jmp dh_orig

; get_timers: eax = SetTimer (0 if user32 cannot be found); KillTimer is stored first
get_timers:
    mov eax, dword ptr [ebp + 0x10056e48]
    test eax, eax
    jne gt_ret
    lea eax, [ebp + txt_user32]
    push eax
    call dword ptr [ebp + 0x10040104]
    test eax, eax
    je gt_ret
    mov esi, eax
    lea ecx, [ebp + txt_killtimer]
    push ecx
    push esi
    call dword ptr [ebp + 0x10040030]
    mov dword ptr [ebp + 0x10056e4c], eax
    lea ecx, [ebp + txt_settimer]
    push ecx
    push esi
    call dword ptr [ebp + 0x10040030]
    mov dword ptr [ebp + 0x10056e48], eax
gt_ret:
    ret

; --- WM_PAINT (0x1003233D, PAINTSTRUCT at [esp+0x10]) and the idle redraw (0x100320EE, window DC in edi)
paint_hook:
    push dword ptr [esp + 0x10]
    call draw_prog
    lea ecx, [esp + 0x10]
    push ecx
    jmp 0x10032342
idle_hook:
    pop ebx
    push edi
    call draw_prog
    mov ecx, dword ptr [ebp + 0x88]
    jmp 0x100320f5

; draw_buttons(hwnd): both buttons, pressed (bitmap 106) or normal (bitmap 101)
draw_buttons:
    pushal
    call db_base
db_base:
    pop ebp
    sub ebp, db_base
    push dword ptr [esp + 0x24]
    call dword ptr [ebp + 0x100401a8]
    test eax, eax
    je db_end
    mov esi, eax
    push esi
    call dword ptr [ebp + 0x1004001c]
    test eax, eax
    je db_rel
    mov edi, eax
    movzx ebx, byte ptr [ebp + 0x10056e43]
    mov eax, 1
    mov ecx, 164
    mov edx, 160
    call db_one
    mov eax, 2
    mov ecx, 221
    mov edx, 175
    call db_one
    push edi
    call dword ptr [ebp + 0x10040024]
db_rel:
    push esi
    push dword ptr [esp + 0x28]
    call dword ptr [ebp + 0x100401ac]
db_end:
    popal
    ret 4
; eax = button (1/2), ecx = panel x, edx = x in bitmap 106; ebx = held button, esi = window DC, edi = memory DC
db_one:
    push ecx
    push edx
    cmp eax, ebx
    jne db_normal
    push dword ptr [ebp + 0x10055338]
    push edi
    call dword ptr [ebp + 0x10040020]
    pop edx
    pop ecx
    push 0xcc0020
    push 0
    push edx
    jmp db_blit
db_normal:
    push dword ptr [ebp + 0x10055320]
    push edi
    call dword ptr [ebp + 0x10040020]
    pop edx
    pop ecx
    push 0xcc0020
    push 4
    push ecx
db_blit:
    push edi
    push 15
    push 15
    push 4
    push ecx
    push esi
    call dword ptr [ebp + 0x10040018]
    ret

; draw_prog(hdc): program of part 1 as 3 digits (blank until the audio thread has seen the engine)
draw_prog:
    pushal
    call dp_base
dp_base:
    pop ebp
    sub ebp, dp_base
    mov esi, dword ptr [esp + 0x24]
    push esi
    call dword ptr [ebp + 0x1004001c]
    test eax, eax
    je dp_end
    mov edi, eax
    push dword ptr [ebp + 0x1005533c]
    push edi
    call dword ptr [ebp + 0x10040020]
    mov ecx, dword ptr [ebp + 0x10056e44]
    test ecx, ecx
    jne dp_value
    mov eax, 10
    mov ecx, 185
    call dp_digit
    mov eax, 10
    mov ecx, 195
    call dp_digit
    mov eax, 10
    jmp dp_last
dp_value:
    mov ecx, dword ptr [ecx + 8]
    movzx ebx, byte ptr [ecx + 0x366]
    inc ebx
    mov eax, ebx
    xor edx, edx
    mov ecx, 100
    div ecx
    mov ecx, 185
    call dp_digit
    mov eax, ebx
    xor edx, edx
    mov ecx, 10
    div ecx
    xor edx, edx
    div ecx
    mov eax, edx
    mov ecx, 195
    call dp_digit
    mov eax, ebx
    xor edx, edx
    mov ecx, 10
    div ecx
    mov eax, edx
dp_last:
    mov ecx, 205
    call dp_digit
    push edi
    call dword ptr [ebp + 0x10040024]
dp_end:
    popal
    ret 4
; eax = digit (10 = blank), ecx = x; esi = target DC, edi = memory DC with bitmap 105
dp_digit:
    imul eax, eax, 10
    push 0xcc0020
    push 0
    push eax
    push edi
    push 13
    push 10
    push 5
    push ecx
    push esi
    call dword ptr [ebp + 0x10040018]
    ret

gm_reset:
    .byte 0xf0, 0x7e, 0x7f, 0x09, 0x01, 0xf7
gs_reset:
    .byte 0xf0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7f, 0x00, 0x41, 0xf7
xg_reset:
    .byte 0xf0, 0x43, 0x10, 0x4c, 0x00, 0x00, 0x7e, 0x00, 0xf7
gm2_reset:
    .byte 0xf0, 0x7e, 0x7f, 0x09, 0x03, 0xf7
txt_user32:
    .ascii "USER32.dll"
    .byte 0
txt_settimer:
    .ascii "SetTimer"
    .byte 0
txt_killtimer:
    .ascii "KillTimer"
    .byte 0
