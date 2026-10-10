; GUI additions, syxg50.dll: GS / XG reset from the Settings page (dialog 111, combo box 0x421) and the
; preset buttons in the panel (program down / up on MIDI channel 1 with a 3-digit readout).
; Code cave at 0x1003FA80, position independent (call/pop, ebp = load delta). State in .data:
;   0x10056E40  pending reset (0 = none, 1 = GS, 2 = XG), set by the dialog, taken by the audio thread
;   0x10056E41  combo box selection (0 = GS, 1 = XG), restored when the page is opened again
;   0x10056E42  pending program step (signed), added by the panel buttons, taken by the audio thread
;   0x10056E43  preset button held (0 = none, 1 = down, 2 = up)
;   0x10056E44  engine (plugin +0xB0), stored by the audio thread for the readout (0 until audio runs)
; Events go through the same entries as host events (engine vtable +0x0C SysEx (engine, data, length),
; +0x08 short message (engine, packed bytes), stdcall), at the start of the next process call.
; Panel (bitmap 101, title strip): buttons 15 x 15 at (164,1) and (221,1), readout digits (bitmap 105,
; 10 x 13) at (185,2), pressed buttons in bitmap 106 at (160,0) and (175,0). The program of part 1 is
; byte +0x366 of the synth object [engine +8] (0-127, shown as 001-128).

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
send_pending:
    pushal
    call sp_base
sp_base:
    pop ebp
    sub ebp, sp_base
    mov edx, dword ptr [esp + 0x28]
    mov ecx, dword ptr [edx + 0x40]
    mov ecx, dword ptr [ecx + 0xb0]
    mov dword ptr [ebp + 0x10056e44], ecx
    test ecx, ecx
    je sp_done
    xor eax, eax
    xchg byte ptr [ebp + 0x10056e40], al
    test eax, eax
    je sp_prog
    cmp eax, 1
    jne sp_xg
    lea esi, [ebp + gs_reset]
    push 11
    jmp sp_send
sp_xg:
    lea esi, [ebp + xg_reset]
    push 9
sp_send:
    push esi
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 0xc]
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

; --- panel window (0x10032260, (this, hwnd, msg, wparam, lparam), locals 0x40 + 4 pushes: hwnd [esp+0x58],
;     lparam [esp+0x64]); WM_LBUTTONDOWN (0x1003246B) and WM_LBUTTONUP (0x10032427) jump here
lbd_hook:
    mov eax, dword ptr [esp + 0x64]
    movsx ecx, ax
    sar eax, 16
    cmp eax, 1
    jl lbd_orig
    cmp eax, 16
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
    push dword ptr [esp + 0x78]
    call draw_buttons
    popal
    jmp 0x100324b3
lbu_none:
    popal
    mov esi, dword ptr [esp + 0x54]
    mov al, byte ptr [esi + 0x8c]
    jmp 0x10032431

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
    push 1
    push ecx
db_blit:
    push edi
    push 15
    push 15
    push 1
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
    push 2
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
    cmp eax, 1
    ja dc_skip
    mov byte ptr [ebp + 0x10056e41], al
    inc eax
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
    push eax
    push 0x14e
    push ebx
    call dword ptr [ebp + 0x10040174]
    popal
    mov eax, dword ptr [esp + 0xc]
dlg_orig:
    add eax, -0x4e
    jmp 0x10030af7

gs_reset:
    .byte 0xf0, 0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7f, 0x00, 0x41, 0xf7
xg_reset:
    .byte 0xf0, 0x43, 0x10, 0x4c, 0x00, 0x00, 0x7e, 0x00, 0xf7
txt_gs:
    .byte 0x47, 0x53, 0
txt_xg:
    .byte 0x58, 0x47, 0
