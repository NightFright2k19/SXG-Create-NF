; GUI additions, syxg50.dll: GM / GS / XG reset from the Settings page (dialog 111, combo box 0x421) and the
; preset buttons in the panel (program down / up on MIDI channel 1 with a 3-digit readout).
; Code cave at 0x10033150 (unused NOP block inside .text, no relocations), position independent
; (call/pop, ebp = load delta). State in .data:
;   0x10056E40  pending reset (0 = none, 1 = GM, 2 = GS, 3 = XG), set by the dialog, taken by the audio thread
;   0x10056E41  combo box selection (0 = GM, 1 = GS, 2 = XG) XOR 2, so the zeroed .data means XG (default)
;   0x10056E42  pending program step (signed), added by the panel buttons / mouse wheel, taken by the audio thread
;   0x10056E43  preset button held (0 = none, 1 = down, 2 = up)
;   0x10056E44  engine (plugin +0xB0), stored by the audio thread for the readout (0 until audio runs)
;   0x10056E48  SetTimer, 0x10056E4C KillTimer (user32, looked up on the first button press)
;   0x10056E50  mouse wheel remainder (WHEEL_DELTA = 120 per step)
;   0x10056E54  samples left until host events may pass again after a reset (4800 = 100 ms at 48 kHz)
;   0x10056E58  event queue (VirtualAlloc 64 KB on the first reset): VstEvents header + 256 pointers at +0,
;               256 events of 32 bytes at +1032, SysEx bytes (32 KB) at +9224
;   0x10056E5C  queued events, 0x10056E60 queued SysEx bytes
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
    xor eax, eax
    xchg byte ptr [ebp + 0x10056e40], al
    test eax, eax
    je sp_queue
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
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 0xc]
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
; q_add: copy host event eax into the queue (edi), deltaFrames 0; SysEx data copied too. Full queue: dropped.
q_add:
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

; --- Settings page procedure (0x10030AF0, (page, hwnd, msg, wparam, lparam), ret 0x14) jumps here
dlg_hook:
    mov eax, dword ptr [esp + 0xc]
    cmp eax, 0x110
    je dlg_init
    cmp eax, 0x111
    jne dlg_orig
    cmp word ptr [esp + 0x10], 0x421
    jne dlg_orig
    cmp word ptr [esp + 0x12], 9
    jne dlg_done
    pushal
    call dc_base
dc_base:
    pop ebp
    sub ebp, dc_base
    push 0x421
    push dword ptr [esp + 0x2c]
    call dword ptr [ebp + 0x10040178]
    push 0
    push 0
    push 0x147
    push eax
    call dword ptr [ebp + 0x10040174]
    cmp eax, 2
    ja dc_skip
    mov ebx, eax
    cmp dword ptr [ebp + 0x10056e58], 0
    jne dc_have
    push 4
    push 0x3000
    push 0x10000
    push 0
    call dword ptr [ebp + 0x1004013c]
    mov dword ptr [ebp + 0x10056e58], eax
dc_have:
    mov eax, ebx
    xor al, 2
    mov byte ptr [ebp + 0x10056e41], al
    lea eax, [ebx + 1]
    mov byte ptr [ebp + 0x10056e40], al
dc_skip:
    popal
dlg_done:
    mov eax, 1
    ret 0x14
dlg_init:
    pushal
    call di_base
di_base:
    pop ebp
    sub ebp, di_base
    push 0x421
    push dword ptr [esp + 0x2c]
    call dword ptr [ebp + 0x10040178]
    mov ebx, eax
    lea eax, [ebp + txt_gm]
    push eax
    push 0
    push 0x143
    push ebx
    call dword ptr [ebp + 0x10040174]
    lea eax, [ebp + txt_gs]
    push eax
    push 0
    push 0x143
    push ebx
    call dword ptr [ebp + 0x10040174]
    lea eax, [ebp + txt_xg]
    push eax
    push 0
    push 0x143
    push ebx
    call dword ptr [ebp + 0x10040174]
    push 0
    movzx eax, byte ptr [ebp + 0x10056e41]
    xor eax, 2
    push eax
    push 0x14e
    push ebx
    call dword ptr [ebp + 0x10040174]
    popal
    mov eax, dword ptr [esp + 0xc]
dlg_orig:
    add eax, -0x4e
    jmp 0x10030af7

gm_reset:
    .byte 0xf0, 0x7e, 0x7f, 0x09, 0x01, 0xf7
gs_reset:
    .byte 0xf0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7f, 0x00, 0x41, 0xf7
xg_reset:
    .byte 0xf0, 0x43, 0x10, 0x4c, 0x00, 0x00, 0x7e, 0x00, 0xf7
txt_gm:
    .byte 0x47, 0x4d, 0
txt_gs:
    .byte 0x47, 0x53, 0
txt_xg:
    .byte 0x58, 0x47, 0
txt_user32:
    .ascii "USER32.dll"
    .byte 0
txt_settimer:
    .ascii "SetTimer"
    .byte 0
txt_killtimer:
    .ascii "KillTimer"
    .byte 0
