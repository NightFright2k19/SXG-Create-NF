; Panel controls in the title strip (issues #16, #23, #35), part of section .sxp (assembled after poly.asm):
;   CHN < 01 >        MIDI channel 1-16 for the selector on the right (not saved, starts at 01)
;   PRE v < 001 >     program of that channel; a click on the label switches PRE -> MSB -> LSB -> PRE (bank
;                     select MSB / LSB 000-127; PRE after loading, not saved)
; Buttons: single click, hold (repeat after 400 ms every 75 ms, panel timer 0x2317), mouse wheel over a control.
; Positions (dev/gui/mkpreset.py, layout.txt; all x plus panel_dx): buttons 15 x 15 at x 118 / 166 (CHN) and 223 / 281, rows 4-18;
; readouts (bitmap 105 digits 10 x 13) at 139 (2 digits) and 244 (3 digits), row 5; switchable label 27 x 15 at
; 193; bitmap 106 holds the pressed buttons at x 160 / 175 and the labels PRE / MSB / LSB at 190 / 217 / 244.
; The values come from the part of the selected channel (part_ptr: the synth [engine +8] keeps the parts in the
; order of channels 10, 1-9, 11-16, records of 0x11C bytes from +0x248: +0 bank MSB, +1 bank LSB, +2 program). A PRE step sends a program change, an MSB / LSB
; step a bank select (CC 0 / CC 32) followed by the program change of the current program, so the new bank
; sounds at once (audio thread, panel_prog, called by send_pending; to both engines). A bank select the engine
; ignores in its current mode (GM: MSB and LSB, GS: LSB) shows as "---" and is not sent.
; .data: 0x10056E42 pending step (signed), 0x10056E43 held button (1 / 2 = value down / up, 3 / 4 = channel
; down / up), 0x10056E44 engine, 0x10056E48 / 0x10056E4C SetTimer / KillTimer, 0x10056E50 wheel remainder,
; 0x10056F00 channel (0-15), 0x10056F01 label (0 = PRE, 1 = MSB, 2 = LSB).

; --- panel_prog (audio thread, from send_pending): pending step -> program change / bank select
panel_prog:
    pushal
    call pp_base
pp_base:
    pop ebp
    sub ebp, pp_base
    xor eax, eax
    xchg byte ptr [ebp + 0x10056e42], al
    test al, al
    je pp_ret
    movsx ebx, al
    mov ecx, dword ptr [ebp + 0x10056e44]
    test ecx, ecx
    je pp_ret
    movzx edi, byte ptr [ebp + 0x10056f00]
    and edi, 15
    mov eax, edi
    call part_ptr
    mov esi, eax
    movzx edx, byte ptr [ebp + 0x10056f01]
    cmp edx, 1
    je pp_msb
    ja pp_lsb
    movzx eax, byte ptr [esi + 2]
    add eax, ebx
    and eax, 0x7f
    call pp_pc
    jmp pp_ret
pp_msb:
    mov ecx, dword ptr [ebp + 0x10056e44]
    call bank_ignored
    jne pp_ret
    movzx eax, byte ptr [esi]
    xor ecx, ecx
    jmp pp_bank
pp_lsb:
    mov ecx, dword ptr [ebp + 0x10056e44]
    call bank_ignored
    jne pp_ret
    movzx eax, byte ptr [esi + 1]
    mov ecx, 32
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
pp_ret:
    popal
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
    xor edx, edx
    call hit_test
    test edx, edx
    je lbd_orig
    pushal
    call lbd_base
lbd_base:
    pop ebp
    sub ebp, lbd_base
    mov ebx, dword ptr [esp + 0x78]
    cmp edx, 5
    jne lbd_button
    movzx eax, byte ptr [ebp + 0x10056f01]
    inc eax
    cmp eax, 3
    jb lbd_mode
    xor eax, eax
lbd_mode:
    mov byte ptr [ebp + 0x10056f01], al
    push ebx
    call redraw_values
    jmp lbd_end
lbd_button:
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

; hit_test: ecx = x (row already checked) -> edx = 1 / 2 value down / up, 3 / 4 channel down / up, 5 label, 0
hit_test:
    push ebp
    call ht_base
ht_base:
    pop ebp
    sub ebp, ht_base
    sub ecx, dword ptr [ebp + panel_dx]
    pop ebp
    xor edx, edx
    mov eax, 3
    cmp ecx, 118
    jl ht_ret
    cmp ecx, 133
    jl ht_hit
    inc eax
    cmp ecx, 166
    jl ht_ret
    cmp ecx, 181
    jl ht_hit
    mov eax, 5
    cmp ecx, 193
    jl ht_ret
    cmp ecx, 220
    jl ht_hit
    mov eax, 1
    cmp ecx, 223
    jl ht_ret
    cmp ecx, 238
    jl ht_hit
    inc eax
    cmp ecx, 281
    jl ht_ret
    cmp ecx, 296
    jge ht_ret
ht_hit:
    mov edx, eax
ht_ret:
    ret

; do_step: edx = held button (1-4): value steps go to the audio thread, channel steps act at once
do_step:
    mov al, 1
    test dl, 1
    je ds_up
    neg al
ds_up:
    cmp dl, 3
    jae ds_chn
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
    sub ecx, dword ptr [ebp + panel_dx]
    cmp edx, 4
    jl dw_out
    cmp edx, 19
    jge dw_out
    mov edi, 3
    cmp ecx, 118
    jl dw_out
    cmp ecx, 181
    jl dw_area
    mov edi, 1
    cmp ecx, 193
    jl dw_out
    cmp ecx, 296
    jge dw_out
dw_area:
    movsx eax, word ptr [esp + 0x82]
    add eax, dword ptr [ebp + 0x10056e50]
    cdq
    mov ecx, 120
    idiv ecx
    mov dword ptr [ebp + 0x10056e50], edx
    cmp edi, 3
    je dw_chn
    lock add byte ptr [ebp + 0x10056e42], al
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

; redraw_values(hwnd): readouts and label through the window DC
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

; draw_buttons(hwnd): the four buttons, pressed (bitmap 106) or normal (bitmap 101)
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
    mov eax, 3
    mov ecx, 118
    mov edx, 160
    call db_one
    mov eax, 4
    mov ecx, 166
    mov edx, 175
    call db_one
    mov eax, 1
    mov ecx, 223
    mov edx, 160
    call db_one
    mov eax, 2
    mov ecx, 281
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
; eax = button, ecx = panel x (without panel_dx), edx = x in bitmap 106; ebx = held button, esi = window DC,
; edi = memory DC
db_one:
    add ecx, dword ptr [ebp + panel_dx]
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

; draw_prog(hdc): label (bitmap 106), channel (2 digits) and the selected value (3 digits; blank until the
; audio thread has seen the engine)
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
    push dword ptr [ebp + 0x10055338]
    push edi
    call dword ptr [ebp + 0x10040020]
    movzx eax, byte ptr [ebp + 0x10056f01]
    imul eax, eax, 27
    add eax, 190
    push 0xcc0020
    push 0
    push eax
    push edi
    push 15
    push 27
    push 4
    mov eax, 193
    add eax, dword ptr [ebp + panel_dx]
    push eax
    push esi
    call dword ptr [ebp + 0x10040018]
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
    mov ecx, 139
    call dp_digit
    pop eax
    mov ecx, 149
    call dp_digit
    mov ecx, dword ptr [ebp + 0x10056e44]
    test ecx, ecx
    jne dp_value
    mov eax, 10
    mov ecx, 244
    call dp_digit
    mov eax, 10
    mov ecx, 254
    call dp_digit
    mov eax, 10
    jmp dp_last
dp_value:
    movzx eax, byte ptr [ebp + 0x10056f00]
    and eax, 15
    call part_ptr
    lea ecx, [eax - 0x364]
    movzx edx, byte ptr [ebp + 0x10056f01]
    cmp edx, 2
    jbe dp_sel
    xor edx, edx
dp_sel:
    xor eax, eax
    cmp edx, 0
    jne dp_bank
    movzx ebx, byte ptr [ecx + 0x366]
    inc ebx
    jmp dp_show
dp_bank:
    push ecx
    mov ecx, dword ptr [ebp + 0x10056e44]
    call bank_ignored
    pop ecx
    jne dp_dashes
    movzx ebx, byte ptr [ecx + edx + 0x363]
dp_show:
    mov eax, ebx
    xor edx, edx
    mov ecx, 100
    div ecx
    mov ecx, 244
    call dp_digit
    mov eax, ebx
    xor edx, edx
    mov ecx, 10
    div ecx
    xor edx, edx
    div ecx
    mov eax, edx
    mov ecx, 254
    call dp_digit
    mov eax, ebx
    xor edx, edx
    mov ecx, 10
    div ecx
    mov eax, edx
dp_last:
    mov ecx, 264
    call dp_digit
    jmp dp_rel
dp_dashes:
    push dword ptr [ebp + 0x10055338]
    push edi
    call dword ptr [ebp + 0x10040020]
    mov ecx, 244
    call dp_dash
    mov ecx, 254
    call dp_dash
    mov ecx, 264
    call dp_dash
dp_rel:
    push edi
    call dword ptr [ebp + 0x10040024]
dp_end:
    popal
    ret 4
; dp_dash: ecx = x; a dash (bitmap 106 at x 271, memory DC edi has bitmap 106 selected)
dp_dash:
    mov eax, 271
    jmp dp_go
; eax = digit (10 = blank), ecx = x; esi = target DC, edi = memory DC with bitmap 105
dp_digit:
    imul eax, eax, 10
dp_go:
    add ecx, dword ptr [ebp + panel_dx]
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

; panel_dx: horizontal offset of both controls, set per model by dllpatch.py (PANEL_DX) so they sit in the
; middle between the YAMAHA logo and the model name: +8 for S-YXG50 / 80 / 90, +4 for S-YXG100 / 128, 0 for S-YXG1000
panel_dx:
    .int 0
txt_user32:
    .ascii "USER32.dll"
    .byte 0
txt_settimer:
    .ascii "SetTimer"
    .byte 0
txt_killtimer:
    .ascii "KillTimer"
    .byte 0
