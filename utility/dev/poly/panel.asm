; Panel controls (issues #16, #23, #35, #42), part of section .sxp (assembled after poly.asm). Since #42 the
; panel is 24 pixels higher (400 x 114) and has a control row of its own under the title strip:
;   CHN < 01 >   PRG < 001 >   MSB < 000 >   LSB < 000 >
; CHN: MIDI channel 1-16 for the three others (not saved, starts at 01); PRG: program of that channel; MSB / LSB:
; its bank select. A bank value the engine ignores in its current mode (GM: MSB and LSB, GS: LSB) shows "---" and
; is not sent. Buttons: single click, hold (repeat after 400 ms every 75 ms, panel timer 0x2317), mouse wheel.
; Positions (bitmap 101 from dev/gui/mkpanel.py): buttons 15 x 15 in row 31, see btn_table; digits (bitmap 105,
; 10 x 13) in row 32 at 46 (CHN, 2), 137 (PRG), 242 (MSB), 344 (LSB); bitmap 106 holds the pressed left / right
; button at x 160 / 175 and a dash at 190.
; The values come from the part of the selected channel (part_ptr: the synth [engine +8] keeps the parts in the
; order of channels 10, 1-9, 11-16, records of 0x11C bytes from +0x248: +0 bank MSB, +1 bank LSB, +2 program).
; A PRG step sends a program change, an MSB / LSB step a bank select (CC 0 / CC 32) followed by the program change
; of the current program, so the new bank sounds at once (audio thread, panel_prog, called by send_pending; to
; both engines).
; .data: 0x10056E42 / 0x10056F01 / 0x10056F02 pending PRG / MSB / LSB step (signed), 0x10056E43 held button
; (1 / 2 PRG down / up, 3 / 4 CHN, 5 / 6 MSB, 7 / 8 LSB), 0x10056E44 engine, 0x10056E48 / 0x10056E4C SetTimer /
; KillTimer, 0x10056E50 wheel remainder, 0x10056F00 channel (0-15).
; Preview note (issue #43): holding the left mouse button in the POLYPHONY field (x 246-297, y 58-101) plays a
; note on the selected channel (velocity 100), the mouse wheel over the field changes the pitch (C1-G9, default
; C4 = 60; a held note is retriggered). .data: 0x10056F04 note XOR 0x3C (zeroed .data = 60), 0x10056F05 note
; sounding + 1 (0 = none, audio thread), 0x10056F06 mouse button held, 0x10056F07 channel of the sounding note.

; --- panel_prog (audio thread, from send_pending): pending steps -> program change / bank select
panel_prog:
    pushal
    call pp_base
pp_base:
    pop ebp
    sub ebp, pp_base
    mov ecx, dword ptr [ebp + 0x10056e44]
    test ecx, ecx
    je pp_ret
    movzx edi, byte ptr [ebp + 0x10056f00]
    and edi, 15
    call pp_prev
    mov eax, edi
    call part_ptr
    mov esi, eax
    xor eax, eax
    xchg byte ptr [ebp + 0x10056e42], al
    test al, al
    je pp_m
    movsx ebx, al
    movzx eax, byte ptr [esi + 2]
    add eax, ebx
    and eax, 0x7f
    call pp_pc
pp_m:
    xor eax, eax
    xchg byte ptr [ebp + 0x10056f01], al
    test al, al
    je pp_l
    movsx ebx, al
    mov edx, 1
    mov ecx, dword ptr [ebp + 0x10056e44]
    call bank_ignored
    jne pp_l
    movzx eax, byte ptr [esi]
    xor ecx, ecx
    call pp_bank
pp_l:
    xor eax, eax
    xchg byte ptr [ebp + 0x10056f02], al
    test al, al
    je pp_ret
    movsx ebx, al
    mov edx, 2
    mov ecx, dword ptr [ebp + 0x10056e44]
    call bank_ignored
    jne pp_ret
    movzx eax, byte ptr [esi + 1]
    mov ecx, 32
    call pp_bank
pp_ret:
    popal
    ret
; pp_prev: the preview note follows the mouse button (held -> note on, released or changed -> note off first);
; edi = channel, keeps all registers
pp_prev:
    pushal
    xor ebx, ebx
    cmp byte ptr [ebp + 0x10056f06], 0
    je pv_cmp
    movzx ebx, byte ptr [ebp + 0x10056f04]
    xor ebx, 0x3c
    inc ebx
pv_cmp:
    movzx eax, byte ptr [ebp + 0x10056f05]
    cmp eax, ebx
    je pv_ret
    test eax, eax
    je pv_on
    dec eax
    shl eax, 8
    or eax, 0x400080
    movzx ecx, byte ptr [ebp + 0x10056f07]
    or eax, ecx
    push eax
    call both_short
pv_on:
    mov byte ptr [ebp + 0x10056f05], bl
    test ebx, ebx
    je pv_ret
    mov eax, edi
    mov byte ptr [ebp + 0x10056f07], al
    lea eax, [ebx - 1]
    shl eax, 8
    or eax, 0x640090
    or eax, edi
    push eax
    call both_short
pv_ret:
    popal
    ret
; pp_bank: eax = current value, ebx = step, ecx = controller (0 / 32), edi = channel, esi = part
pp_bank:
    add eax, ebx
    and eax, 0x7f
    shl eax, 16
    shl ecx, 8
    or eax, ecx
    or eax, 0xb0
    or eax, edi
    push eax
    call both_short
    movzx eax, byte ptr [esi + 2]
    call pp_pc
    ret
; bank_ignored: ecx = engine, edx = 1 (MSB) or 2 (LSB) -> ZF clear (jne) if the engine ignores that bank select
; in its current mode: after a GM reset both (synth +0x63B0 = 1; 0 = XG, 2 = GM2), after a GS reset the LSB
; (synth +0x63AE = 0, else 1)
bank_ignored:
    push ecx
    mov ecx, dword ptr [ecx + 8]
    cmp byte ptr [ecx + 0x63b0], 1
    je bi_yes
    cmp edx, 2
    jne bi_no
    cmp byte ptr [ecx + 0x63ae], 0
    je bi_yes
bi_no:
    pop ecx
    cmp eax, eax
    ret
bi_yes:
    pop ecx
    or ecx, ecx
    or esp, esp
    ret
; part_ptr: eax = channel (0-15), ecx = engine -> eax = bank MSB of that channel's part (+1 LSB, +2 program).
; The synth keeps the parts in the order 10, 1-9, 11-16 (records of 0x11C bytes from +0x248)
part_ptr:
    push edx
    mov edx, eax
    cmp eax, 9
    je pt_drum
    jg pt_rec
    inc edx
    jmp pt_rec
pt_drum:
    xor edx, edx
pt_rec:
    imul edx, edx, 0x11c
    mov eax, dword ptr [ecx + 8]
    lea eax, [eax + edx + 0x248]
    pop edx
    ret
; pp_pc: program eax on channel edi
pp_pc:
    shl eax, 8
    or eax, 0xc0
    or eax, edi
    push eax
    call both_short
    ret

; button table: held code, x (row 31, 15 x 15); odd codes step down, even up
btn_table:
    .int 3, 25, 4, 73, 1, 116, 2, 174, 5, 221, 6, 279, 7, 323, 8, 381

; --- panel window (0x10032260, (this, hwnd, msg, wparam, lparam), locals 0x40 + 4 pushes: hwnd [esp+0x58],
;     wparam [esp+0x60], lparam [esp+0x64]); WM_LBUTTONDOWN (0x1003246B), WM_LBUTTONUP (0x10032427) and the
;     DefWindowProc branch (0x10032407: WM_TIMER, WM_MOUSEWHEEL) jump here
lbd_hook:
    mov eax, dword ptr [esp + 0x64]
    movsx ecx, ax
    sar eax, 16
    cmp eax, 31
    jl lbd_orig
    cmp eax, 46
    jge lbd_prev
    call hit_test
    test edx, edx
    je lbd_orig
    pushal
    call lbd_base
lbd_base:
    pop ebp
    sub ebp, lbd_base
    mov ebx, dword ptr [esp + 0x78]
    mov byte ptr [ebp + 0x10056e43], dl
    call do_step
    push ebx
    call dword ptr [ebp + 0x100401a4]
    push ebx
    call draw_buttons
    push ebx
    call redraw_values
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
; preview note: left button in the POLYPHONY field, eax = y, ecx = x
lbd_prev:
    cmp eax, 58
    jl lbd_orig
    cmp eax, 102
    jge lbd_orig
    cmp ecx, 246
    jl lbd_orig
    cmp ecx, 298
    jge lbd_orig
    pushal
    call lbp_base
lbp_base:
    pop ebp
    sub ebp, lbp_base
    mov byte ptr [ebp + 0x10056f06], 1
    push dword ptr [esp + 0x78]
    call dword ptr [ebp + 0x100401a4]
    popal
    jmp 0x100324b3

; hit_test: ecx = x (row already checked) -> edx = button code (0 = none)
hit_test:
    push ebp
    push esi
    call ht_base
ht_base:
    pop ebp
    sub ebp, ht_base
    lea esi, [ebp + btn_table]
    xor edx, edx
ht_loop:
    mov eax, dword ptr [esi + edx * 8 + 4]
    cmp ecx, eax
    jl ht_next
    add eax, 15
    cmp ecx, eax
    jge ht_next
    mov edx, dword ptr [esi + edx * 8]
    jmp ht_ret
ht_next:
    inc edx
    cmp edx, 8
    jb ht_loop
    xor edx, edx
ht_ret:
    pop esi
    pop ebp
    ret

; do_step: edx = button code: the channel steps at once, PRG / MSB / LSB steps go to the audio thread
do_step:
    mov al, 1
    test dl, 1
    je ds_up
    neg al
ds_up:
    cmp dl, 3
    jb ds_pre
    cmp dl, 5
    jb ds_chn
    cmp dl, 7
    jb ds_msb
    lock add byte ptr [ebp + 0x10056f02], al
    ret
ds_msb:
    lock add byte ptr [ebp + 0x10056f01], al
    ret
ds_pre:
    lock add byte ptr [ebp + 0x10056e42], al
    ret
ds_chn:
    add al, byte ptr [ebp + 0x10056f00]
    and al, 15
    mov byte ptr [ebp + 0x10056f00], al
    ret

lbu_hook:
    pushal
    call lbu_base
lbu_base:
    pop ebp
    sub ebp, lbu_base
    cmp byte ptr [ebp + 0x10056f06], 0
    je lbu_btn
    mov byte ptr [ebp + 0x10056f06], 0
    call dword ptr [ebp + 0x100401a0]
    popal
    jmp 0x100324b3
lbu_btn:
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
    call do_step
    push ebx
    call redraw_values
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
    cmp edx, 31
    jl dw_out
    cmp edx, 46
    jl dw_ctl
    cmp edx, 58
    jl dw_out
    cmp edx, 102
    jge dw_out
    cmp ecx, 246
    jl dw_out
    cmp ecx, 298
    jge dw_out
    mov edi, 10
    jmp dw_area
dw_ctl:
    mov edi, 4                               ; group by x: CHN 25-87, PRG 116-188, MSB 221-293, LSB 323-395
    cmp ecx, 25
    jl dw_out
    cmp ecx, 88
    jl dw_area
    mov edi, 2
    cmp ecx, 116
    jl dw_out
    cmp ecx, 189
    jl dw_area
    mov edi, 6
    cmp ecx, 221
    jl dw_out
    cmp ecx, 294
    jl dw_area
    mov edi, 8
    cmp ecx, 323
    jl dw_out
    cmp ecx, 396
    jge dw_out
dw_area:
    movsx eax, word ptr [esp + 0x82]
    add eax, dword ptr [ebp + 0x10056e50]
    cdq
    mov ecx, 120
    idiv ecx
    mov dword ptr [ebp + 0x10056e50], edx
    cmp edi, 10
    je dw_note
    cmp edi, 4
    je dw_chn
    cmp edi, 2
    je dw_pre
    cmp edi, 6
    je dw_msb
    lock add byte ptr [ebp + 0x10056f02], al
    jmp dw_draw
dw_msb:
    lock add byte ptr [ebp + 0x10056f01], al
    jmp dw_draw
dw_pre:
    lock add byte ptr [ebp + 0x10056e42], al
    jmp dw_draw
dw_note:
    movsx eax, al
    movzx edx, byte ptr [ebp + 0x10056f04]
    xor edx, 0x3c
    add edx, eax
    cmp edx, 24
    jge dw_n1
    mov edx, 24
dw_n1:
    cmp edx, 127
    jle dw_n2
    mov edx, 127
dw_n2:
    xor edx, 0x3c
    mov byte ptr [ebp + 0x10056f04], dl
    jmp dw_draw
dw_chn:
    add al, byte ptr [ebp + 0x10056f00]
    and al, 15
    mov byte ptr [ebp + 0x10056f00], al
dw_draw:
    push dword ptr [esp + 0x78]
    call redraw_values
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

; redraw_values(hwnd): readouts through the window DC
redraw_values:
    pushal
    call rv_base
rv_base:
    pop ebp
    sub ebp, rv_base
    push dword ptr [esp + 0x24]
    call dword ptr [ebp + 0x100401a8]
    test eax, eax
    je rv_end
    mov esi, eax
    push esi
    call draw_prog
    push esi
    push dword ptr [esp + 0x28]
    call dword ptr [ebp + 0x100401ac]
rv_end:
    popal
    ret 4

; draw_buttons(hwnd): the eight buttons, pressed (bitmap 106) or normal (bitmap 101)
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
    xor edx, edx
db_loop:
    push edx
    lea eax, [ebp + btn_table]
    mov ecx, dword ptr [eax + edx * 8 + 4]
    mov eax, dword ptr [eax + edx * 8]
    call db_one
    pop edx
    inc edx
    cmp edx, 8
    jb db_loop
    push edi
    call dword ptr [ebp + 0x10040024]
db_rel:
    push esi
    push dword ptr [esp + 0x28]
    call dword ptr [ebp + 0x100401ac]
db_end:
    popal
    ret 4
; db_one: eax = button code, ecx = x; ebx = held button, esi = window DC, edi = memory DC
db_one:
    push ecx
    cmp eax, ebx
    jne db_normal
    mov edx, 175                             ; pressed: bitmap 106, left (odd code) at 160, right at 175
    test al, 1
    je db_pr
    mov edx, 160
db_pr:
    push edx
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
    pop ecx
    push 0xcc0020
    push 31
    push ecx
db_blit:
    push edi
    push 15
    push 15
    push 31
    push ecx
    push esi
    call dword ptr [ebp + 0x10040018]
    ret

; draw_prog(hdc): channel (2 digits) and program (PRG) / bank MSB / bank LSB (3 digits each) of that channel; blank until
; the audio thread has seen the engine, "---" for a bank value the engine ignores
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
    movzx ebx, byte ptr [ebp + 0x10056f00]
    and ebx, 15
    inc ebx
    mov eax, ebx
    xor edx, edx
    mov ecx, 10
    div ecx
    push edx
    mov ecx, 46
    call dp_digit
    pop eax
    mov ecx, 56
    call dp_digit
    mov ecx, dword ptr [ebp + 0x10056e44]
    test ecx, ecx
    jne dp_values
    mov ebx, -1
    mov ecx, 137
    call dp_three
    mov ecx, 242
    call dp_three
    mov ecx, 344
    call dp_three
    jmp dp_rel
dp_values:
    movzx eax, byte ptr [ebp + 0x10056f00]
    and eax, 15
    call part_ptr
    mov edx, eax                             ; edx = part (MSB, LSB, program)
    push edx
    movzx ebx, byte ptr [edx + 2]
    inc ebx
    mov ecx, 137
    call dp_three
    pop edx
    push edx
    movzx ebx, byte ptr [edx]
    push edx
    mov edx, 1
    mov ecx, dword ptr [ebp + 0x10056e44]
    call bank_ignored
    pop edx
    je dp_msb
    mov ebx, -2
dp_msb:
    mov ecx, 242
    call dp_three
    pop edx
    movzx ebx, byte ptr [edx + 1]
    mov edx, 2
    mov ecx, dword ptr [ebp + 0x10056e44]
    call bank_ignored
    je dp_lsb
    mov ebx, -2
dp_lsb:
    mov ecx, 344
    call dp_three
dp_rel:
    push edi
    call dword ptr [ebp + 0x10040024]
dp_end:
    popal
    ret 4
; dp_three: ebx = value (-1 blank, -2 dashes), ecx = x of the first digit
dp_three:
    cmp ebx, -2
    je dt3_dash
    push ecx
    mov eax, ebx
    cmp ebx, -1
    jne dt3_d1
    mov eax, 10
    call dp_digit
    pop ecx
    push ecx
    add ecx, 10
    mov eax, 10
    call dp_digit
    pop ecx
    add ecx, 20
    mov eax, 10
    jmp dp_digit
dt3_d1:
    xor edx, edx
    push ecx
    mov ecx, 100
    div ecx
    pop ecx
    call dp_digit
    pop ecx
    push ecx
    add ecx, 10
    mov eax, ebx
    xor edx, edx
    push ecx
    mov ecx, 10
    div ecx
    xor edx, edx
    div ecx
    mov eax, edx
    pop ecx
    call dp_digit
    pop ecx
    add ecx, 20
    mov eax, ebx
    xor edx, edx
    push ecx
    mov ecx, 10
    div ecx
    mov eax, edx
    pop ecx
    jmp dp_digit
dt3_dash:
    push ecx                                 ; SelectObject changes ecx
    push dword ptr [ebp + 0x10055338]
    push edi
    call dword ptr [ebp + 0x10040020]
    pop ecx
    push ecx
    call dp_dash
    pop ecx
    push ecx
    add ecx, 10
    call dp_dash
    pop ecx
    add ecx, 20
    call dp_dash
    push dword ptr [ebp + 0x1005533c]
    push edi
    call dword ptr [ebp + 0x10040020]
    ret
; dp_dash: ecx = x; a dash (bitmap 106 at x 190, memory DC edi has bitmap 106 selected)
dp_dash:
    mov eax, 190
    jmp dp_go
; dp_digit: eax = digit (10 = blank), ecx = x; esi = target DC, edi = memory DC with bitmap 105
dp_digit:
    imul eax, eax, 10
dp_go:
    push 0xcc0020
    push 0
    push eax
    push edi
    push 13
    push 10
    push 32
    push ecx
    push esi
    call dword ptr [ebp + 0x10040018]
    ret

txt_user32:
    .ascii "USER32.dll"
    .byte 0
txt_settimer:
    .ascii "SetTimer"
    .byte 0
txt_killtimer:
    .ascii "KillTimer"
    .byte 0
