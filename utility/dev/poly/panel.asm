; Panel controls (issues #16, #23, #35, #42), part of section .sxp (assembled after poly.asm). Since #42 the
; panel is 24 pixels higher (400 x 114) and has a control row of its own under the title strip:
;   CHN < 01 >   PRG < 001 >   MSB < 000 >   LSB < 000 >
; CHN: MIDI channel 1-16 for the three others (not saved, starts at 01); PRG: program of that channel; MSB / LSB:
; its bank select. A bank value the engine ignores in its current mode (GM: MSB and LSB, GS: LSB) shows "---" and
; is not sent. Buttons: single click, hold (repeat after 400 ms every 75 ms, panel timer 0x2317), mouse wheel.
; Positions (bitmap 101 from dev/gui/mkpanel.py): buttons 15 x 15 in row 31, see btn_table; digits (bitmap 105,
; 10 x 13) in row 32 at 46 (CHN, 2), 137 (PRG), 242 (MSB), 344 (LSB); bitmap 106 holds the pressed left / right
; button at x 160 / 175, a dash at 190 the dimmed digits for a drum part's PRG at x 200 (issue #70) and the red ones for a part without an instrument at x 300 (issue #73).
; The values come from the part of the selected channel (part_ptr: the synth [engine +8] keeps the parts in the
; order of channels 10, 1-9, 11-16, records of 0x11C bytes from +0x248: +0 bank MSB, +1 bank LSB, +2 program).
; A PRG step sends a program change (on a drum part a step goes on to the next kit the engine takes, issue #70), an MSB / LSB step a bank select (CC 0 / CC 32) followed by the program change
; of the current program, so the new bank sounds at once (audio thread, panel_prog, called by send_pending; to
; engine A and the B of its slot).
; Per instance (issue #55): hosts such as VST Midi Driver run several instances in one process, so nothing the
; panel shows or sends may sit in a process-wide variable. The panel object keeps its engine at [panel +8]
; (= plugin +0xB0); the panel state lives in a panel record of that engine, 4 records x 16 bytes at 0x10056F08:
; +0 engine (claimed with lock cmpxchg by the panel, freed at effClose), +4 / +5 / +6 pending PRG / MSB / LSB
; step (signed), +7 channel (0-15), +8 note XOR 0x3C (zeroed = 60), +9 note sounding + 1 (0 = none, audio
; thread), +0xA mouse button held in the POLYPHONY field, +0xB channel of the sounding note, +0xC 1 once the
; audio thread has processed that engine (the readouts stay blank until then).
; .data (UI thread only): 0x10056E43 held button (1 / 2 PRG down / up, 3 / 4 CHN, 5 / 6 MSB, 7 / 8 LSB),
; 0x10056E48 / 0x10056E4C SetTimer / KillTimer, 0x10056E50 wheel remainder.
; Preview note (issue #43): holding the left mouse button in the POLYPHONY field (x 245-298, y 57-103) plays a
; note on the selected channel (velocity 100, engine A only, issue #46), the mouse wheel over the field changes the
; pitch (C1-G9, default C4 = 60; a held note is retriggered).

; --- panel_prog (audio thread, from send_pending, esi = plugin A): pending steps -> program change / bank select
panel_prog:
    pushal
    call pp_base
pp_base:
    pop ebp
    sub ebp, pp_base
    mov eax, dword ptr [esi + 0xb0]
    call rec_find
    test eax, eax
    je pp_ret
    mov ebx, eax                             ; ebx = panel record of this plugin's engine
    mov byte ptr [ebx + 0xc], 1
    movzx edi, byte ptr [ebx + 7]
    and edi, 15
    call pp_prev
    mov eax, edi
    mov ecx, dword ptr [ebx]
    call part_ptr
    mov esi, eax
    xor eax, eax
    xchg byte ptr [ebx + 4], al
    test al, al
    je pp_m
    movsx edx, al                            ; edx = step, ecx = program of the part
    movzx ecx, byte ptr [esi + 2]
    lea eax, [ecx + edx]
    and eax, 0x7f
    call pp_pc                               ; (keeps ecx / edx)
; Issue #70: a drum part only has a few kits (GS / GM2: programs 0, 8, 16, 24, 25, 32, 40, 48, 56, 127) and the engine ignores
; any other program change from the panel, so a step stayed on the same kit. Go on in the direction of the step (round
; the ring of 128 programs, like a step on a melodic part) until the engine takes a program. A melodic part takes the first.
    test edx, edx
    js pp_dn
    mov edx, 1                               ; edx = distance of the program change that was sent
pp_up:
    cmp byte ptr [esi + 2], cl
    jne pp_m
    cmp edx, 127
    jae pp_m
    inc edx
    lea eax, [ecx + edx]
    and eax, 0x7f
    call pp_pc
    jmp pp_up
pp_dn:
    mov edx, 1
pp_dnl:
    cmp byte ptr [esi + 2], cl
    jne pp_m
    cmp edx, 127
    jae pp_m
    inc edx
    mov eax, ecx
    sub eax, edx
    and eax, 0x7f
    call pp_pc
    jmp pp_dnl
pp_m:
    xor eax, eax
    xchg byte ptr [ebx + 5], al
    test al, al
    je pp_l
    mov edx, 1
    mov ecx, dword ptr [ebx]
    call bank_ignored
    jne pp_l
    movsx eax, al
    movzx ecx, byte ptr [esi]
    add eax, ecx
    xor ecx, ecx
    call pp_bank
pp_l:
    xor eax, eax
    xchg byte ptr [ebx + 6], al
    test al, al
    je pp_ret
    mov edx, 2
    mov ecx, dword ptr [ebx]
    call bank_ignored
    jne pp_ret
    movsx eax, al
    movzx ecx, byte ptr [esi + 1]
    add eax, ecx
    mov ecx, 32
    call pp_bank
pp_ret:
    popal
    ret
; pp_prev: the preview note follows the mouse button (held -> note on, released or changed -> note off first);
; ebx = panel record, edi = channel, keeps all registers
pp_prev:
    pushal
    xor esi, esi
    cmp byte ptr [ebx + 0xa], 0
    je pv_cmp
    movzx esi, byte ptr [ebx + 8]
    xor esi, 0x3c
    inc esi
pv_cmp:
    movzx eax, byte ptr [ebx + 9]
    cmp eax, esi
    je pv_ret
    test eax, eax
    je pv_on
    dec eax
    shl eax, 8
    or eax, 0x400080
    movzx ecx, byte ptr [ebx + 0xb]
    or eax, ecx
    call pv_send
pv_on:
    mov eax, esi
    mov byte ptr [ebx + 9], al
    test esi, esi
    je pv_ret
    mov eax, edi
    mov byte ptr [ebx + 0xb], al
    lea eax, [esi - 1]
    shl eax, 8
    or eax, 0x640090
    or eax, edi
    call pv_send
pv_ret:
    popal
    ret
; pv_send: eax = message, ebx = panel record; to engine A only (short-message entry, vtable +8). Engine B renders
; only while the dispatcher has given it notes, so a note sent to it here would keep a voice and count in
; POLYPHONY (issue #46)
pv_send:
    mov ecx, dword ptr [ebx]
    push eax
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 8]
    ret
; pp_bank: eax = new value, ecx = controller (0 / 32), ebx = panel record, edi = channel, esi = part
pp_bank:
    and eax, 0x7f
    shl eax, 16
    shl ecx, 8
    or eax, ecx
    or eax, 0xb0
    or eax, edi
    call rec_short
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
; pp_pc: program eax on channel edi, ebx = panel record
pp_pc:
    shl eax, 8
    or eax, 0xc0
    or eax, edi
    call rec_short
    ret
; rec_short: eax = message to the engine of panel record ebx and to the B of its slot; keeps all registers
rec_short:
    pushal
    mov edi, dword ptr [ebx]
    push eax
    push eax
    push edi
    mov edx, dword ptr [edi]
    call dword ptr [edx + 8]
    call slot_of_engine
    pop eax
    test ebx, ebx
    je rs_ret
    mov ecx, dword ptr [ebx + 4]
    mov ecx, dword ptr [ecx + 0x40]
    mov ecx, dword ptr [ecx + 0xb0]
    push eax
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 8]
rs_ret:
    popal
    ret

; rec_find: eax = engine -> eax = its panel record (0 if none); rec_claim: the same, claims a free record for an
; engine that has none (lock cmpxchg; 0 if all four are in use). Both keep the other registers and find their
; own load delta, so the window hooks can call them with ebp = anything.
rec_find:
    push ebx
    xor ebx, ebx
    jmp rc_go
rec_claim:
    push ebx
    mov ebx, 1
rc_go:
    push ecx
    push edx
    push ebp
    call rc_base
rc_base:
    pop ebp
    sub ebp, rc_base
    mov edx, eax
    xor eax, eax
    test edx, edx
    je rc_ret
    lea eax, [ebp + 0x10056f08]
    mov ecx, 4
rc_find:
    cmp dword ptr [eax], edx
    je rc_ret
    add eax, 16
    loop rc_find
    xor eax, eax
    test ebx, ebx
    je rc_ret
    lea ebx, [ebp + 0x10056f08]
    mov ecx, 4
rc_claim:
    xor eax, eax
    lock cmpxchg dword ptr [ebx], edx
    je rc_got
    add ebx, 16
    loop rc_claim
    xor eax, eax
    jmp rc_ret
rc_got:
    mov eax, ebx
rc_ret:
    pop ebp
    pop edx
    pop ecx
    pop ebx
    ret
; ui_rec: eax = panel object -> eax = panel record of its engine ([panel +8]), claimed if needed
ui_rec:
    mov eax, dword ptr [eax + 8]
    jmp rec_claim

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
    mov eax, dword ptr [esp + 0x74]
    call ui_rec
    mov esi, eax
    mov byte ptr [ebp + 0x10056e43], dl
    call do_step
    push ebx
    call dword ptr [ebp + 0x100401a4]
    push ebx
    call draw_buttons
    push esi
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
    cmp eax, 57
    jl lbd_orig
    cmp eax, 104
    jge lbd_orig
    cmp ecx, 245
    jl lbd_orig
    cmp ecx, 299
    jge lbd_orig
    pushal
    call lbp_base
lbp_base:
    pop ebp
    sub ebp, lbp_base
    mov eax, dword ptr [esp + 0x74]
    call ui_rec
    test eax, eax
    je lbp_cap
    mov byte ptr [eax + 0xa], 1
lbp_cap:
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

; do_step: edx = button code, esi = panel record (0: nothing): the channel steps at once, PRG / MSB / LSB steps
; go to the audio thread
do_step:
    test esi, esi
    je ds_ret
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
    lock add byte ptr [esi + 6], al
    ret
ds_msb:
    lock add byte ptr [esi + 5], al
    ret
ds_pre:
    lock add byte ptr [esi + 4], al
    ret
ds_chn:
    add al, byte ptr [esi + 7]
    and al, 15
    mov byte ptr [esi + 7], al
ds_ret:
    ret

lbu_hook:
    pushal
    call lbu_base
lbu_base:
    pop ebp
    sub ebp, lbu_base
    mov eax, dword ptr [esp + 0x74]
    call ui_rec
    test eax, eax
    je lbu_btn
    cmp byte ptr [eax + 0xa], 0
    je lbu_btn
    mov byte ptr [eax + 0xa], 0
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
    mov eax, dword ptr [esp + 0x74]
    call ui_rec
    mov esi, eax
    call do_step
    push esi
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
    cmp edx, 57
    jl dw_out
    cmp edx, 104
    jge dw_out
    cmp ecx, 245
    jl dw_out
    cmp ecx, 299
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
    mov eax, dword ptr [esp + 0x74]
    call ui_rec
    mov esi, eax
    test esi, esi
    je dw_out
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
    lock add byte ptr [esi + 6], al
    jmp dw_draw
dw_msb:
    lock add byte ptr [esi + 5], al
    jmp dw_draw
dw_pre:
    lock add byte ptr [esi + 4], al
    jmp dw_draw
dw_note:
    movsx eax, al
    movzx edx, byte ptr [esi + 8]
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
    mov byte ptr [esi + 8], dl
    jmp dw_draw
dw_chn:
    add al, byte ptr [esi + 7]
    and al, 15
    mov byte ptr [esi + 7], al
dw_draw:
    push esi
    push dword ptr [esp + 0x7c]
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
    mov eax, dword ptr [esp + 0x54]
    call ui_rec
    push eax
    push dword ptr [esp + 0x14]
    call draw_prog
    lea ecx, [esp + 0x10]
    push ecx
    jmp 0x10032342
idle_hook:
    pop ebx
    mov eax, ebp
    call ui_rec
    push eax
    push edi
    call draw_prog
    mov ecx, dword ptr [ebp + 0x88]
    jmp 0x100320f5

; redraw_values(hwnd, record): readouts through the window DC
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
    push dword ptr [esp + 0x28]
    push esi
    call draw_prog
    push esi
    push dword ptr [esp + 0x28]
    call dword ptr [ebp + 0x100401ac]
rv_end:
    popal
    ret 8

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

; draw_prog(hdc, record): channel (2 digits) and program (PRG) / bank MSB / bank LSB (3 digits each) of that channel;
; blank until the audio thread has processed the record's engine (or without a record), "---" for a bank value the
; engine ignores
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
    mov eax, dword ptr [esp + 0x28]           ; panel record
    xor ebx, ebx
    test eax, eax
    je dp_chn
    movzx ebx, byte ptr [eax + 7]
    and ebx, 15
dp_chn:
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
    mov ecx, dword ptr [esp + 0x28]
    test ecx, ecx
    je dp_blank
    cmp byte ptr [ecx + 0xc], 0
    jne dp_values
dp_blank:
    mov ebx, -1
    mov ecx, 137
    call dp_three
    mov ecx, 242
    call dp_three
    mov ecx, 344
    call dp_three
    jmp dp_rel
dp_values:
    movzx eax, byte ptr [ecx + 7]
    and eax, 15
    mov ecx, dword ptr [ecx]
    call part_ptr
    mov edx, eax                             ; edx = part (MSB, LSB, program)
    push edx
    movzx ebx, byte ptr [edx + 2]
    inc ebx
    call drum_part                           ; edx = part
    test eax, eax
    jne dp_prg_drum
    call no_voice                            ; ecx = engine (kept by part_ptr and drum_part), edx = part
    mov ecx, 137
    test eax, eax
    je dp_prg
    call dp_three_red                        ; a melodic part without a valid instrument: red digits (issue #73)
    jmp dp_prg_done
dp_prg_drum:
    mov ecx, 137
    call dp_three_dim                        ; a drum part: dimmed digits (issue #70)
    jmp dp_prg_done
dp_prg:
    call dp_three
dp_prg_done:
    pop edx
    push edx
    movzx ebx, byte ptr [edx]
    push edx
    mov edx, 1
    mov ecx, dword ptr [esp + 0x30]
    mov ecx, dword ptr [ecx]
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
    mov ecx, dword ptr [esp + 0x28]
    mov ecx, dword ptr [ecx]
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
    ret 8
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
; drum_part: edx = part -> eax = 1 for a drum part, else 0 (keeps the other registers). Byte +0x92 of the part record is the
; engine's own rhythm flag: 0 for a melodic part, 2 / 3 (drum map 1 / 2) for a drum part. It follows every way a part becomes
; or stops being a drum part: GS "use for rhythm part" on any channel, bank MSB 120 / 126 / 127 in XG (channel 10 always is
; one in the S-YXG engines), GM2 (MSB 120 / 126 / 127 drum, 121 melodic) and GM (channel 10); in GS the banks 120 / 127 are
; only variations and leave it 0. It is set by the program change that follows a bank select (the panel shows the engine's state).
drum_part:
    xor eax, eax
    cmp byte ptr [edx + 0x92], 0
    setne al
    ret
; dp_three_dim: ebx = value 0-999, ecx = x: three dimmed digits (bitmap 106 at x 200 + 10 * digit, selected into the memory DC
; edi meanwhile), no blanks and no dashes
dp_three_dim:
    push ecx                                 ; SelectObject changes ecx
    push dword ptr [ebp + 0x10055338]
    push edi
    call dword ptr [ebp + 0x10040020]
    pop ecx
    push ecx
    mov eax, ebx
    xor edx, edx
    push ecx
    mov ecx, 100
    div ecx
    pop ecx
    call dp_digit_dim
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
    call dp_digit_dim
    pop ecx
    add ecx, 20
    mov eax, ebx
    xor edx, edx
    push ecx
    mov ecx, 10
    div ecx
    mov eax, edx
    pop ecx
    call dp_digit_dim
    push dword ptr [ebp + 0x1005533c]
    push edi
    call dword ptr [ebp + 0x10040020]
    ret
dp_digit_dim:
    imul eax, eax, 10
    add eax, 200
    jmp dp_go
; no_voice: ecx = engine, edx = part -> eax = 1 for a part that has no instrument (issue #73). The engine has no flag for it:
; it looks the voice up at each note (the function at 0x10004540: stdcall (synth, bank MSB, bank LSB, program) -> pointer to the
; voice), and a bank or program without a voice gets the voice of its silent bank (XG: SFX MSB 1, in XG and GM2 mode all its
; programs). So the part has no instrument when its voice is the one of MSB 1 / LSB 0 / program 0. In GS mode (+0x63AE = 0
; after a GS reset) an unknown bank falls back on a capital tone, so only MSB 126 with a program from 64 up (silent) counts. The caller has
; excluded drum parts (they keep ignoring a program without a kit). ebx, esi, edi, ebp are kept; the engine's function keeps them too.
no_voice:
    push esi
    push edi
    mov esi, dword ptr [ecx + 8]             ; the synth
    xor eax, eax
    cmp byte ptr [esi + 0x63ae], al
    jne nv_xg
    cmp byte ptr [edx], 126                  ; GS: bank MSB 126 has voices for programs 0-63 only
    jne nv_ret
    cmp byte ptr [edx + 2], 64
    setae al
    jmp nv_ret
nv_xg:
    movzx eax, byte ptr [edx + 2]
    push eax                                 ; program
    movzx eax, byte ptr [edx + 1]
    push eax                                 ; bank LSB
    movzx eax, byte ptr [edx]
    push eax                                 ; bank MSB
    push esi
    call 0x10004540
    mov edi, eax                             ; the part's voice
    push 0
    push 0
    push 1
    push esi
    call 0x10004540                          ; the voice of the silent bank
    cmp eax, edi
    sete al
    movzx eax, al
nv_ret:
    pop edi
    pop esi
    ret
; dp_three_red: like dp_three_dim, with the red digits (bitmap 106 at x 300 + 10 * digit)
dp_three_red:
    push ecx                                 ; SelectObject changes ecx
    push dword ptr [ebp + 0x10055338]
    push edi
    call dword ptr [ebp + 0x10040020]
    pop ecx
    push ecx
    mov eax, ebx
    xor edx, edx
    push ecx
    mov ecx, 100
    div ecx
    pop ecx
    call dp_digit_red
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
    call dp_digit_red
    pop ecx
    add ecx, 20
    mov eax, ebx
    xor edx, edx
    push ecx
    mov ecx, 10
    div ecx
    mov eax, edx
    pop ecx
    call dp_digit_red
    push dword ptr [ebp + 0x1005533c]
    push edi
    call dword ptr [ebp + 0x10040020]
    ret
dp_digit_red:
    imul eax, eax, 10
    add eax, 300
    jmp dp_go
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
