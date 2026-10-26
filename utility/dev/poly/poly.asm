; Polyphony 256 for syxg50.dll (issue #14): a second synth engine (instance B) inside the DLL.
; Code in the new section .sxp at 0x1005B000 (inserted in front of .rsrc), position independent (call/pop, ebp =
; load delta). Entry points: poly_procR (processReplacing wrapper 0x100010C0), poly_procA (process wrapper
; 0x100010A0), both_sysex (stdcall data, len) and both_short (stdcall packed message) for gui.asm, poly_disp
; (dispatcher 0x10001000: effClose closes instance B). Addresses come from mkgui.py.
; .data:
;   0x10056EB8  extra voices above 128 (0-128, Settings page / plugin state) XOR 0x80, so the zeroed .data means
;               128 extra voices (256 in total, the default); total = 128 + extra
;   0x10056EB9  extra voices on the Settings page (before Apply)
;   0x10056EBC  unused (was the slot being processed; shared state broke parallel processing)
;   0x10056EC0  4 slots x 16 bytes: +0 plugin object A, +4 AEffect of instance B, +8 samples B stays awake,
;               +0xC event lists (16 KB: list A at +0, list B at +0x2008)
;   0x10056F08  4 panel records x 16 bytes (panel.asm, issue #55), freed at effClose
; Port engines (issue #74, experimental): F5 02 / 03 / 04 make one more instance each (create_inst, same as B), kept in three
; pseudo-slots after the slot's list block (init_ext: +0x3008 current port, +0x3010 pseudo-slots, +0x3040 last reset SysEx,
; lists at +0x4000 / +0x5010 / +0x6020). route sends channel messages of port 2-4 to that port's list only and SysEx and
; system messages to all; a GM / XG / GS reset selects port 1. Ports render after B (pm_ports), ports have 128 voices.
; Instance B is created (VSTPluginMain 0x10003610, own audioMaster stub) in the first block of the plugin and
; then gets all events, so it always knows the song's state; notes go to it only with extra voices. Every block: B gets the settings of A (Set 0x10030770 on B's settings object; effect switches,
; Output Level, polyphony = extra), the host's events are split: a Note On goes to A while A has two voices
; free (synth +0x64BE, minus two per Note On already given to A in this block), else to B while B has two
; free, else to A (A steals). Everything else goes to both. B renders (process, accumulating, after A) while it
; has voices and 4 s longer (release, reverb); asleep, it only takes its events through the engine entries.

; --- process wrappers: send_pending (gui.asm) as before, then A, then B
poly_procR:
    pushal
    call slot_setup
    popal
    call SEND_PENDING
    pushal
    mov edi, 0x14
    jmp poly_main
poly_procA:
    pushal
    call slot_setup
    popal
    call SEND_PENDING
    pushal
    mov edi, 0x10
; after pushal: host return [esp+0x20], effect [esp+0x24], inputs +0x28, outputs +0x2c, frames +0x30
poly_main:
    call pm_base
pm_base:
    pop ebp
    sub ebp, pm_base
    mov eax, dword ptr [esp + 0x24]
    mov esi, dword ptr [eax + 0x40]
    lea ebx, [ebp + 0x10056ec0]
    mov ecx, 4
pm_find:
    cmp dword ptr [ebx], esi
    jne pm_fn
    cmp dword ptr [ebx + 4], 0
    jne pm_found
pm_fn:
    add ebx, 16
    loop pm_find
    xor ebx, ebx
pm_found:
    test ebx, ebx
    je pm_a
    push edi
    call sync_b
    call sync_ports
    call route
    pop edi
pm_a:
    mov ecx, esi
    mov edx, dword ptr [ecx]
    push dword ptr [esp + 0x30]
    push dword ptr [esp + 0x30]
    push dword ptr [esp + 0x30]
    call dword ptr [edx + edi]
    test ebx, ebx
    je pm_done
    cmp dword ptr [ebx + 8], 0
    jle pm_ports
    mov eax, dword ptr [ebx + 4]
    mov ecx, dword ptr [eax + 0x40]
    mov eax, dword ptr [ebx + 0xc]
    add eax, 0x2008
    cmp dword ptr [eax], 0
    jne pm_list
    xor eax, eax
pm_list:
    mov dword ptr [ecx + 0xe0], eax
    push ecx
    mov edx, dword ptr [ecx]
    push dword ptr [esp + 0x34]
    push dword ptr [esp + 0x34]
    push dword ptr [esp + 0x34]
    call dword ptr [edx + 0x10]
    pop ecx
    mov dword ptr [ecx + 0xe0], 0
    ; voices left in B? (free < polyphony) -> stay awake 4 s longer, else count down
    mov eax, dword ptr [ecx + 0xb0]
    mov eax, dword ptr [eax + 8]
    movzx edx, word ptr [eax + 0x64be]
    cmp dx, word ptr [eax + 0x64c0]
    jae pm_idle
    mov eax, dword ptr [esi + 0xd8]
    shl eax, 2
    mov dword ptr [ebx + 8], eax
    jmp pm_ports
pm_idle:
    mov eax, dword ptr [esp + 0x30]
    sub dword ptr [ebx + 8], eax
    jg pm_ports
    mov dword ptr [ebx + 8], 0
; port instances (F5 02 .. 04, issue #74): the pseudo-slots after the slot's list block, same rules as B
pm_ports:
    mov eax, dword ptr [ebx + 0xc]
    lea ebx, [eax + 0x3010]
    push 3
pp_loop:
    cmp dword ptr [ebx + 4], 0
    je pp_next
    cmp dword ptr [ebx + 8], 0
    jle pp_next
    mov eax, dword ptr [ebx + 4]
    mov ecx, dword ptr [eax + 0x40]
    mov eax, dword ptr [ebx + 0xc]
    cmp dword ptr [eax], 0
    jne pp_list
    xor eax, eax
pp_list:
    mov dword ptr [ecx + 0xe0], eax
    push ecx
    mov edx, dword ptr [ecx]
    push dword ptr [esp + 0x38]
    push dword ptr [esp + 0x38]
    push dword ptr [esp + 0x38]
    call dword ptr [edx + 0x10]
    pop ecx
    mov dword ptr [ecx + 0xe0], 0
    mov eax, dword ptr [ecx + 0xb0]
    mov eax, dword ptr [eax + 8]
    movzx edx, word ptr [eax + 0x64be]
    cmp dx, word ptr [eax + 0x64c0]
    jae pp_idle
    mov eax, dword ptr [esi + 0xd8]
    shl eax, 2
    mov dword ptr [ebx + 8], eax
    jmp pp_next
pp_idle:
    mov eax, dword ptr [esp + 0x34]
    sub dword ptr [ebx + 8], eax
    jg pp_next
    mov dword ptr [ebx + 8], 0
pp_next:
    add ebx, 16
    dec dword ptr [esp]
    jne pp_loop
    add esp, 4
pm_done:
    popal
    ret

; --- slot_setup (after pushal; effect at [esp+0x28]): finds or claims the slot of plugin A and creates its
;     instance B when there is none yet. Hosts may process several instances in parallel threads, so a free slot
;     is claimed with lock cmpxchg and nothing about the current slot is kept in shared .data (poly_main and
;     both_sysex / both_short look their slot up themselves).
slot_setup:
    call ss_base
ss_base:
    pop ebp
    sub ebp, ss_base
    mov eax, dword ptr [esp + 0x28]
    mov esi, dword ptr [eax + 0x40]
    lea ebx, [ebp + 0x10056ec0]
    mov ecx, 4
ss_find:
    cmp dword ptr [ebx], esi
    je ss_have
    add ebx, 16
    loop ss_find
    lea ebx, [ebp + 0x10056ec0]
    mov ecx, 4
ss_claim:
    xor eax, eax
    lock cmpxchg dword ptr [ebx], esi
    je ss_have
    add ebx, 16
    loop ss_claim
    ret
ss_have:
    cmp dword ptr [ebx + 4], 0
    jne ss_ret
    call create_b
ss_ret:
    ret

; create_b: ebx = free slot, esi = plugin A
create_b:
    cmp dword ptr [ebx + 0xc], 0
    jne cb_main
    push 4
    push 0x3000
    push 0x8000
    push 0
    call dword ptr [ebp + 0x1004013c]
    test eax, eax
    je cb_ret
    mov dword ptr [ebx + 0xc], eax
cb_main:
    call init_ext
; create_inst: ebx = slot or pseudo-slot, esi = plugin A
create_inst:
    lea eax, [ebp + fake_am]
    push eax
    call 0x10003610
    add esp, 4
    test eax, eax
    je cb_ret
    mov dword ptr [ebx + 8], 0
    mov dword ptr [ebx + 4], eax
    xor ecx, ecx
    xor edx, edx
    call disp_b
    call set_rate
cb_ret:
    ret

; init_ext (ebx = slot): extension of the list block (issue #74): +0x3008 current port (0-3), +0x3040 the last reset SysEx
;     seen (length, bytes at +0x3044, at most 16; a new port instance gets it), +0x3010 3 pseudo-slots of
;     16 bytes (like a slot: +4 AEffect of the port instance for F5 02 / 03 / 04, +8 samples awake, +0xC its event list),
;     lists at +0x4000, +0x5010, +0x6020 (block 0x8000 bytes)
init_ext:
    push eax
    push ecx
    push edx
    mov edx, dword ptr [ebx + 0xc]
    mov dword ptr [edx + 0x3008], 0
    mov dword ptr [edx + 0x3040], 0
    lea ecx, [edx + 0x3010]
    lea eax, [edx + 0x4000]
    push 3
ie_loop:
    mov dword ptr [ecx], 0
    mov dword ptr [ecx + 4], 0
    mov dword ptr [ecx + 8], 0
    mov dword ptr [ecx + 0xc], eax
    add ecx, 16
    add eax, 0x1010
    dec dword ptr [esp]
    jne ie_loop
    add esp, 4
    pop edx
    pop ecx
    pop eax
    ret

; set_rate: instance B (slot ebx) gets sample rate and block size of A (esi): mains off, rate, block, mains on
set_rate:
    mov ecx, 12
    xor edx, edx
    call disp_b
    push dword ptr [esi + 0xd8]
    fild dword ptr [esp]
    fstp dword ptr [esp]
    pop eax
    mov ecx, 10
    xor edx, edx
    call disp_bf
    mov ecx, 11
    mov edx, dword ptr [esi + 0x1c]
    call disp_b
    mov ecx, 12
    mov edx, 1
    call disp_b
    mov ecx, 71
    xor edx, edx
    call disp_b
    ret
; disp_b: dispatcher of B (slot ebx), opcode ecx, value edx; disp_bf: same with opt (float bits) eax
disp_b:
    xor eax, eax
disp_bf:
    push eax
    push 0
    push edx
    push 0
    push ecx
    mov eax, dword ptr [ebx + 4]
    push eax
    call dword ptr [eax + 4]
    add esp, 24
    ret

; audioMaster of instance B: version 2400, nothing else
fake_am:
    xor eax, eax
    cmp dword ptr [esp + 8], 1
    jne fa_ret
    mov eax, 2400
fa_ret:
    ret

; --- sync_b (esi = A, ebx = slot): sample rate, settings (polyphony of B = extra voices, at least 8). The
;     settings live in the plugin's engine object ([plugin +0xB0], vtable 0x1004E110: Set 0x10030770 = vtable
;     +0x1C, settings at +0x0D), a separate heap block (find_set).
sync_b:
    xor edx, edx
    jmp sync_x
; sync_p: same for a port instance (ebx = its pseudo-slot): polyphony fixed at 128, the Settings value is for A / B
sync_p:
    mov edx, 1
sync_x:
    mov eax, dword ptr [ebx + 4]
    mov edi, dword ptr [eax + 0x40]
    mov eax, dword ptr [esi + 0xd8]
    cmp eax, dword ptr [edi + 0xd8]
    je sb_set
    push edi
    push edx
    call set_rate
    pop edx
    pop edi
sb_set:
    mov eax, esi
    call find_set
    test eax, eax
    je sb_ret
    mov ecx, eax
    mov eax, edi
    call find_set
    test eax, eax
    je sb_ret
    mov edi, eax
    sub esp, 8
    mov eax, dword ptr [ecx + 0xd]
    mov dword ptr [esp], eax
    mov al, byte ptr [ecx + 0x11]
    mov byte ptr [esp + 4], al
    mov al, byte ptr [ebp + 0x10056eb8]
    xor al, 0x80
    cmp al, 8
    jae sb_poly
    mov al, 8
sb_poly:
    test edx, edx
    je sb_pw
    mov al, 128
sb_pw:
    mov byte ptr [esp], al
    mov eax, dword ptr [esp]
    cmp eax, dword ptr [edi + 0xd]
    jne sb_call
    mov al, byte ptr [esp + 4]
    cmp al, byte ptr [edi + 0x11]
    je sb_out
sb_call:
    mov eax, esp
    push eax
    push 0
    push edi
    call 0x10030770
sb_out:
    add esp, 8
sb_ret:
    ret
; sync_ports (ebx = slot, esi = A): settings of A to every port instance
sync_ports:
    push ebx
    mov eax, dword ptr [ebx + 0xc]
    lea ebx, [eax + 0x3010]
    push 3
sp_loop:
    cmp dword ptr [ebx + 4], 0
    je sp_next
    call sync_p
sp_next:
    add ebx, 16
    dec dword ptr [esp]
    jne sp_loop
    add esp, 4
    pop ebx
    ret
; find_set: eax = plugin object -> eax = its settings object (engine object [plugin +0xB0], vtable 0x1004E110;
;     0 if it is not there)
find_set:
    push edx
    mov eax, dword ptr [eax + 0xb0]
    test eax, eax
    je fs_none
    lea edx, [ebp + 0x1004e110]
    cmp dword ptr [eax], edx
    je fs_ret
fs_none:
    xor eax, eax
fs_ret:
    pop edx
    ret

; --- route (esi = A, ebx = slot): split the host events [A+0xE0] into list A and list B
route:
    call clear_ports
    mov edx, dword ptr [ebx + 0xc]
    mov dword ptr [edx], 0
    mov dword ptr [edx + 4], 0
    mov dword ptr [edx + 0x2008], 0
    mov dword ptr [edx + 0x200c], 0
    mov ecx, dword ptr [esi + 0xe0]
    test ecx, ecx
    je rt_asleep
    ; free voices: A in [esp], B in [esp+4] (B only with extra voices)
    mov eax, dword ptr [esi + 0xb0]
    mov eax, dword ptr [eax + 8]
    movzx eax, word ptr [eax + 0x64be]
    push 0
    push eax
    cmp byte ptr [ebp + 0x10056eb8], 0x80
    je rt_go
    mov eax, dword ptr [ebx + 4]
    mov eax, dword ptr [eax + 0x40]
    mov eax, dword ptr [eax + 0xb0]
    mov eax, dword ptr [eax + 8]
    movzx eax, word ptr [eax + 0x64be]
    mov dword ptr [esp + 4], eax
rt_go:
    push ebx
    xor ebx, ebx
rt_loop:
    cmp ebx, dword ptr [ecx]
    jge rt_end
    cmp ebx, 1024
    jge rt_end
    mov eax, dword ptr [ecx + ebx*4 + 8]
    ; ports (issue #74): F5 nn selects the port, channel messages of a port go to its instance only, SysEx and
    ; system messages go to everybody, a reset selects port 1 again
    cmp dword ptr [eax], 1
    jne rt_nm
    movzx edi, byte ptr [eax + 0x18]
    cmp edi, 0xf5
    je rt_psel
    cmp edi, 0xf0
    jae rt_sysev
    call get_port
    test edi, edi
    je rt_orig
    call add_port
    jmp rt_next
rt_psel:
    call port_select
    jmp rt_next
rt_sysev:
    call add_ports
    jmp rt_orig
rt_nm:
    cmp dword ptr [eax], 6
    jne rt_orig
    call sysex_ports
    ; XG part data (parts 17-64) and GS block B go to the instance of their port only, part data of port 1 to A / B only
    call sysex_part
    cmp edi, -1
    jne rt_pt
    call add_ports
    jmp rt_orig
rt_pt:
    test edi, edi
    je rt_orig
    jmp rt_next
rt_orig:
    cmp dword ptr [eax], 1
    jne rt_both
    mov edi, dword ptr [eax + 0x18]
    and edi, 0xf0
    cmp edi, 0x90
    jne rt_both
    cmp byte ptr [eax + 0x1a], 0
    je rt_both
    cmp dword ptr [esp + 4], 2
    jl rt_tryb
    sub dword ptr [esp + 4], 2
    jmp rt_toa
rt_tryb:
    cmp dword ptr [esp + 8], 2
    jl rt_toa
    sub dword ptr [esp + 8], 2
    mov edi, dword ptr [esp]
    cmp dword ptr [edi + 8], 0
    jg rt_tob
    mov dword ptr [edi + 8], -1
    jmp rt_tob
rt_both:
    call add_a
rt_tob:
    push edx
    add edx, 0x2008
    call add_ev
    pop edx
    jmp rt_next
rt_toa:
    call add_a
rt_next:
    inc ebx
    jmp rt_loop
rt_end:
    pop ebx
    add esp, 8
    mov eax, edx
    cmp dword ptr [eax], 0
    jne rt_seta
    xor eax, eax
rt_seta:
    mov dword ptr [esi + 0xe0], eax
    ; B woken by a note (-1): stays awake 4 s and takes A's control-rate clock (+0xE4..+0xEC), so its
    ; envelopes and LFOs run in step with A; asleep: B's events go straight to its engine
    cmp dword ptr [ebx + 8], -1
    jne rt_asleep
    mov eax, dword ptr [esi + 0xd8]
    shl eax, 2
    mov dword ptr [ebx + 8], eax
    mov eax, dword ptr [ebx + 4]
    mov eax, dword ptr [eax + 0x40]
    mov ecx, dword ptr [esi + 0xe4]
    mov dword ptr [eax + 0xe4], ecx
    mov ecx, dword ptr [esi + 0xe8]
    mov dword ptr [eax + 0xe8], ecx
    mov ecx, dword ptr [esi + 0xec]
    mov dword ptr [eax + 0xec], ecx
rt_asleep:
    cmp dword ptr [ebx + 8], 0
    jg rt_ret
    mov edx, dword ptr [ebx + 0xc]
    add edx, 0x2008
    mov eax, dword ptr [ebx + 4]
    mov eax, dword ptr [eax + 0x40]
    mov edi, dword ptr [eax + 0xb0]
    xor ecx, ecx
rt_direct:
    cmp ecx, dword ptr [edx]
    jge rt_clear
    mov eax, dword ptr [edx + ecx*4 + 8]
    push ecx
    push edx
    call to_engine
    pop edx
    pop ecx
    inc ecx
    jmp rt_direct
rt_clear:
    mov dword ptr [edx], 0
rt_ret:
    call deliver_ports
    ret
add_a:
add_ev:
    ; event eax appended to the list at edx
    push ecx
    mov ecx, dword ptr [edx]
    mov dword ptr [edx + ecx*4 + 8], eax
    inc dword ptr [edx]
    pop ecx
    ret
; --- port instances (issue #74). Helpers of route get the slot at [esp + 4] (the route's own push), registers as noted
; clear_ports (ebx = slot): empty the three port lists
clear_ports:
    push edx
    mov edx, dword ptr [ebx + 0xc]
    mov dword ptr [edx + 0x7100], 0
    mov dword ptr [edx + 0x4000], 0
    mov dword ptr [edx + 0x4004], 0
    mov dword ptr [edx + 0x5010], 0
    mov dword ptr [edx + 0x5014], 0
    mov dword ptr [edx + 0x6020], 0
    mov dword ptr [edx + 0x6024], 0
    pop edx
    ret
; sysex_part: SysEx eax. edi = -1: goes to everybody (eax may then be a converted copy); 0: part data of port 1; 1-3: part data of that
; port, a copy with the part moved to port 1 is appended to the list of the port (dropped when it has no instance, or when it is
; longer than 64 bytes or more than 20 copies were made in this block). XG: F0 43 1n 4C 08 pp .. (pp 16-63; no checksum).
; GS (address a1 a2 a3): 40 1x / 41 = part and drum setup of block A (port 1 only), 50 1x / 51 = block B (-> 40 1x / 41 on port 2,
; the checksum rises by 0x10). Patch Common and effects 40 0x / 50 0x: mode 1 (one common set): 50 00 becomes 40 00, to everybody; mode 2:
; 40 00 to port 1, 50 00 to port 2 as 40 00. GS reset 40 00 7F: mode 1 to everybody, mode 2 to the current port only.
; Scratch copies: block + 0x7100 count, +0x7110 entries of 0x60 bytes (event 0x20 + data 0x40).
; Stack: [esp] = kind (0 XG, 1 GS block B, 2 GS common B in mode 1, 3 the original event), then ecx edx ebx esi, the return address, the slot
sysex_part:
    push ecx
    push edx
    push ebx
    push esi
    push 0
    mov edx, dword ptr [eax + 0x18]
    mov ecx, dword ptr [eax + 0x10]
    mov edi, -1
    cmp ecx, 8
    jb spx_ret
    cmp byte ptr [edx + 1], 0x43
    jne spx_gs
    cmp byte ptr [edx + 3], 0x4c
    jne spx_ret
    mov bl, byte ptr [edx + 2]
    and bl, 0xf0
    cmp bl, 0x10
    jne spx_ret
    cmp byte ptr [edx + 4], 8
    jne spx_ret
    movzx edi, byte ptr [edx + 5]
    cmp edi, 64
    jb spx_xg
    mov edi, -1
    jmp spx_ret
spx_xg:
    shr edi, 4
    jmp spx_have
spx_gs:
    cmp byte ptr [edx + 1], 0x41
    jne spx_ret
    cmp byte ptr [edx + 3], 0x42
    jne spx_ret
    cmp byte ptr [edx + 4], 0x12
    jne spx_ret
    mov esi, dword ptr [esp + 0x18]
    mov esi, dword ptr [esi + 0xc]
    movzx ebx, byte ptr [edx + 5]
    cmp bl, 0x41
    je spx_a_only
    cmp bl, 0x51
    je spx_b_conv
    cmp bl, 0x40
    je spx_g40
    cmp bl, 0x50
    jne spx_ret
    mov bh, byte ptr [edx + 6]
    and bh, 0xf0
    je spx_g50c
    cmp bh, 0x10
    je spx_b_conv
    jmp spx_ret
spx_g50c:
    cmp dword ptr [esi + 0x300c], 0
    jne spx_b_conv
    mov dword ptr [esp], 2
    jmp spx_scratch
spx_b_conv:
    mov edi, 1
    mov dword ptr [esp], 1
    jmp spx_have
spx_a_only:
    xor edi, edi
    jmp spx_ret
spx_g40:
    mov bh, byte ptr [edx + 6]
    and bh, 0xf0
    je spx_g40c
    cmp bh, 0x10
    jne spx_ret
    xor edi, edi
    jmp spx_ret
spx_g40c:
    cmp dword ptr [esi + 0x300c], 0
    je spx_ret
    cmp byte ptr [edx + 6], 0
    jne spx_a_only
    cmp byte ptr [edx + 7], 0x7f
    jne spx_a_only
    mov edi, dword ptr [esi + 0x3008]
    test edi, edi
    je spx_ret
    mov dword ptr [esp], 3
spx_have:
    test edi, edi
    je spx_ret
    cmp dword ptr [esp], 3
    je spx_have3
    cmp ecx, 0x40
    ja spx_ret
spx_have3:
    mov ebx, dword ptr [esp + 0x18]
    mov ebx, dword ptr [ebx + 0xc]
    mov esi, edi
    shl esi, 4
    cmp dword ptr [ebx + esi + 0x3004], 0
    je spx_ret
    cmp dword ptr [esp], 3
    jne spx_scratch
    mov edx, dword ptr [ebx + esi + 0x300c]
    call add_ev
    jmp spx_ret
spx_scratch:
    mov ebx, dword ptr [esp + 0x18]
    mov ebx, dword ptr [ebx + 0xc]
    cmp ecx, 0x40
    ja spx_ret
    mov esi, dword ptr [ebx + 0x7100]
    cmp esi, 20
    jae spx_ret
    inc dword ptr [ebx + 0x7100]
    imul esi, esi, 0x60
    push edi
    lea edi, [ebx + esi + 0x7110]
    push edi
    mov esi, eax
    mov ecx, 0x20
    rep movsb
    mov ecx, dword ptr [eax + 0x10]
    mov esi, dword ptr [eax + 0x18]
    push edi
    rep movsb
    pop edi
    mov eax, dword ptr [esp]
    mov dword ptr [eax + 0x18], edi
    cmp dword ptr [esp + 8], 0
    jne spx_gsc
    and byte ptr [edi + 5], 15
    jmp spx_add
spx_gsc:
    sub byte ptr [edi + 5], 0x10
    mov edx, dword ptr [eax + 0x10]
    cmp byte ptr [edi + edx - 1], 0xf7
    jne spx_cs
    dec edx
spx_cs:
    add byte ptr [edi + edx - 1], 0x10
    and byte ptr [edi + edx - 1], 0x7f
spx_add:
    cmp dword ptr [esp + 8], 2
    je spx_k2
    mov edx, dword ptr [esp + 4]
    shl edx, 4
    mov ebx, dword ptr [esp + 0x20]
    mov ebx, dword ptr [ebx + 0xc]
    mov edx, dword ptr [ebx + edx + 0x300c]
    call add_ev
    mov edi, dword ptr [esp + 4]
    add esp, 8
    jmp spx_ret
spx_k2:
    mov edi, -1
    add esp, 8
spx_ret:
    add esp, 4
    pop esi
    pop ebx
    pop edx
    pop ecx
    ret
; get_port: edi = current port 0-3
get_port:
    mov edi, dword ptr [esp + 4]
    mov edi, dword ptr [edi + 0xc]
    mov edi, dword ptr [edi + 0x3008]
    ret
; add_port: event eax to the list of port edi (1-3), dropped when that port has no instance
add_port:
    push ecx
    push edx
    mov ecx, dword ptr [esp + 0xc]
    mov ecx, dword ptr [ecx + 0xc]
    shl edi, 4
    lea ecx, [ecx + edi + 0x3000]
    cmp dword ptr [ecx + 4], 0
    je ap_ret
    mov edx, dword ptr [ecx + 0xc]
    call add_ev
ap_ret:
    pop edx
    pop ecx
    ret
; add_ports: event eax to the lists of all port instances
add_ports:
    push ebx
    push ecx
    push edx
    mov ebx, dword ptr [esp + 0x10]
    mov ebx, dword ptr [ebx + 0xc]
    lea ebx, [ebx + 0x3010]
    mov ecx, 3
aps_loop:
    cmp dword ptr [ebx + 4], 0
    je aps_next
    mov edx, dword ptr [ebx + 0xc]
    call add_ev
aps_next:
    add ebx, 16
    dec ecx
    jne aps_loop
    pop edx
    pop ecx
    pop ebx
    ret
; port_select: F5 nn (event eax). nn 1 = port 1, 2-4 = ports 2-4 (the instance is made at the first F5), others ignored
port_select:
    push ebx
    push ecx
    push edx
    movzx ecx, byte ptr [eax + 0x19]
    cmp ecx, 1
    jb ps_ret
    cmp ecx, 4
    ja ps_ret
    dec ecx
    mov edx, dword ptr [esp + 0x10]
    mov edx, dword ptr [edx + 0xc]
    mov dword ptr [edx + 0x3008], ecx
    test ecx, ecx
    je ps_ret
    shl ecx, 4
    lea ebx, [edx + ecx + 0x3000]
    cmp dword ptr [ebx + 4], 0
    jne ps_ret
    pushal
    call create_inst
    call sync_p
    popal
    mov ecx, dword ptr [edx + 0x3040]
    test ecx, ecx
    je ps_ret
    lea eax, [edx + 0x3044]
    mov edi, dword ptr [ebx + 4]
    mov edi, dword ptr [edi + 0x40]
    mov edi, dword ptr [edi + 0xb0]
    push ecx
    push eax
    push edi
    mov edx, dword ptr [edi]
    call dword ptr [edx + 0xc]
    call keep_awake
ps_ret:
    pop edx
    pop ecx
    pop ebx
    ret
; sysex_ports: a GM / XG / GS reset in the SysEx eax selects port 1 again
sysex_ports:
    push ecx
    push edx
    mov edx, dword ptr [eax + 0x18]
    mov ecx, dword ptr [eax + 0x10]
    cmp ecx, 5
    jb sx_ret
    cmp byte ptr [edx + 1], 0x7e
    jne sx_xg
    cmp byte ptr [edx + 3], 9
    je sx_reset
    jmp sx_ret
sx_xg:
    cmp ecx, 8
    jb sx_ret
    cmp byte ptr [edx + 1], 0x43
    jne sx_gs
    cmp byte ptr [edx + 3], 0x4c
    jne sx_ret
    cmp byte ptr [edx + 4], 0
    jne sx_ret
    cmp byte ptr [edx + 5], 0
    jne sx_ret
    cmp byte ptr [edx + 6], 0x7e
    je sx_reset
    jmp sx_ret
sx_gs:
    cmp byte ptr [edx + 1], 0x41
    jne sx_ret
    cmp byte ptr [edx + 3], 0x42
    jne sx_ret
    cmp byte ptr [edx + 4], 0x12
    jne sx_ret
    cmp byte ptr [edx + 5], 0
    jne sx_gs2
    ; System Mode Set 00 00 7F dd: dd = 0 mode 1 (single module), 1 mode 2 (double module), kept at +0x300C
    cmp byte ptr [edx + 6], 0
    jne sx_ret
    cmp byte ptr [edx + 7], 0x7f
    jne sx_ret
    cmp ecx, 9
    jb sx_ret
    movzx ecx, byte ptr [edx + 8]
    and ecx, 1
    push edi
    mov edi, dword ptr [esp + 0x10]
    mov edi, dword ptr [edi + 0xc]
    mov dword ptr [edi + 0x300c], ecx
    pop edi
    jmp sx_ret
sx_gs2:
    cmp byte ptr [edx + 5], 0x40
    jne sx_ret
    cmp byte ptr [edx + 6], 0
    jne sx_ret
    cmp byte ptr [edx + 7], 0x7f
    jne sx_ret
    ; GS reset in mode 2 only resets the module of the current port (sysex_part sends it there): no port change
    push edi
    mov edi, dword ptr [esp + 0x10]
    mov edi, dword ptr [edi + 0xc]
    cmp dword ptr [edi + 0x300c], 0
    pop edi
    jne sx_ret
sx_reset:
    push edi
    push esi
    mov edi, dword ptr [esp + 0x14]
    mov edi, dword ptr [edi + 0xc]
    mov dword ptr [edi + 0x3008], 0
    cmp ecx, 16
    ja sx_end
    mov dword ptr [edi + 0x3040], ecx
    lea edi, [edi + 0x3044]
    mov esi, edx
    rep movsb
sx_end:
    pop esi
    pop edi
sx_ret:
    pop edx
    pop ecx
    ret
; deliver_ports (ebx = slot, esi = A): a sleeping port instance with a Note On in its list wakes (4 s, A's control
; clock) and renders the list; one without takes its events straight into the engine, like B
deliver_ports:
    pushal
    mov eax, dword ptr [ebx + 0xc]
    lea ebx, [eax + 0x3010]
    push 3
dp_loop:
    cmp dword ptr [ebx + 4], 0
    je dp_next
    mov edx, dword ptr [ebx + 0xc]
    cmp dword ptr [edx], 0
    je dp_next
    cmp dword ptr [ebx + 8], 0
    jg dp_next
    xor ecx, ecx
dp_scan:
    cmp ecx, dword ptr [edx]
    jge dp_direct
    mov eax, dword ptr [edx + ecx*4 + 8]
    inc ecx
    cmp dword ptr [eax], 1
    jne dp_scan
    mov edi, dword ptr [eax + 0x18]
    and edi, 0xf0
    cmp edi, 0x90
    jne dp_scan
    cmp byte ptr [eax + 0x1a], 0
    je dp_scan
    mov eax, dword ptr [esi + 0xd8]
    shl eax, 2
    mov dword ptr [ebx + 8], eax
    mov eax, dword ptr [ebx + 4]
    mov eax, dword ptr [eax + 0x40]
    mov ecx, dword ptr [esi + 0xe4]
    mov dword ptr [eax + 0xe4], ecx
    mov ecx, dword ptr [esi + 0xe8]
    mov dword ptr [eax + 0xe8], ecx
    mov ecx, dword ptr [esi + 0xec]
    mov dword ptr [eax + 0xec], ecx
    jmp dp_next
dp_direct:
    mov eax, dword ptr [ebx + 4]
    mov eax, dword ptr [eax + 0x40]
    mov edi, dword ptr [eax + 0xb0]
    xor ecx, ecx
dp_dl:
    cmp ecx, dword ptr [edx]
    jge dp_clr
    mov eax, dword ptr [edx + ecx*4 + 8]
    push ecx
    push edx
    call to_engine
    pop edx
    pop ecx
    inc ecx
    jmp dp_dl
dp_clr:
    mov dword ptr [edx], 0
dp_next:
    add ebx, 16
    dec dword ptr [esp]
    jne dp_loop
    add esp, 4
    popal
    ret
; close_ports (ebx = slot): close the port instances and forget the port
close_ports:
    push ebx
    mov eax, dword ptr [ebx + 0xc]
    lea ebx, [eax + 0x3010]
    push 3
cp_loop:
    cmp dword ptr [ebx + 4], 0
    je cp_next
    mov ecx, 12
    xor edx, edx
    call disp_b
    mov ecx, 1
    xor edx, edx
    call disp_b
    mov dword ptr [ebx + 4], 0
    mov dword ptr [ebx + 8], 0
cp_next:
    add ebx, 16
    dec dword ptr [esp]
    jne cp_loop
    add esp, 4
    pop ebx
    mov eax, dword ptr [ebx + 0xc]
    mov dword ptr [eax + 0x3008], 0
    ret

; to_engine: event eax to engine edi (MIDI: entry +0x08, SysEx: +0x0C), like the engine's own event loop
to_engine:
    cmp dword ptr [eax], 1
    jne te_sx
    push dword ptr [eax + 0x18]
    push edi
    mov edx, dword ptr [edi]
    call dword ptr [edx + 8]
    ret
te_sx:
    cmp dword ptr [eax], 6
    jne te_ret
    push dword ptr [eax + 0x10]
    push dword ptr [eax + 0x18]
    push edi
    mov edx, dword ptr [edi]
    call dword ptr [edx + 0xc]
    call keep_awake
te_ret:
    ret
; keep_awake (ebx = slot): a SysEx (reset, setup) only takes full effect while the engine renders, so B stays
; awake at least 250 ms after one
keep_awake:
    mov eax, dword ptr [ebx + 4]
    mov eax, dword ptr [eax + 0x40]
    mov ecx, dword ptr [eax + 0xd8]
    shr ecx, 2
    cmp dword ptr [ebx + 8], ecx
    jge ka_ret
    mov dword ptr [ebx + 8], ecx
ka_ret:
    ret

; --- both_sysex (data, len), both_short (message): to engine A (0x10056E44) and to B of the current slot
both_sysex:
    pushal
    call bx_base
bx_base:
    pop ebp
    sub ebp, bx_base
    mov edi, dword ptr [ebp + 0x10056e44]
    call bx_one
    call slot_of_engine
    test ebx, ebx
    je bx_out
    mov eax, dword ptr [ebx + 4]
    mov eax, dword ptr [eax + 0x40]
    mov edi, dword ptr [eax + 0xb0]
    call bx_one
    call keep_awake
    mov eax, dword ptr [ebx + 0xc]
    lea ebx, [eax + 0x3010]
    mov esi, 3
bp_loop:
    mov eax, dword ptr [ebx + 4]
    test eax, eax
    je bp_next
    mov eax, dword ptr [eax + 0x40]
    mov edi, dword ptr [eax + 0xb0]
    call bx_one
    call keep_awake
bp_next:
    add ebx, 16
    dec esi
    jne bp_loop
bx_out:
    popal
    ret 8
; slot_of_engine: edi = engine of plugin A -> ebx = its slot with an instance B (0 if none)
slot_of_engine:
    lea ebx, [ebp + 0x10056ec0]
    mov ecx, 4
se_find:
    mov eax, dword ptr [ebx]
    test eax, eax
    je se_next
    cmp edi, dword ptr [eax + 0xb0]
    jne se_next
    cmp dword ptr [ebx + 4], 0
    jne se_ret
se_next:
    add ebx, 16
    loop se_find
    xor ebx, ebx
se_ret:
    ret
bx_one:
    push dword ptr [esp + 0x2c]
    push dword ptr [esp + 0x2c]
    push edi
    mov edx, dword ptr [edi]
    call dword ptr [edx + 0xc]
    ret
both_short:
    pushal
    call bs_base
bs_base:
    pop ebp
    sub ebp, bs_base
    mov edi, dword ptr [ebp + 0x10056e44]
    call bs_one
    call slot_of_engine
    test ebx, ebx
    je bs_out
    mov eax, dword ptr [ebx + 4]
    mov eax, dword ptr [eax + 0x40]
    mov edi, dword ptr [eax + 0xb0]
    call bs_one
bs_out:
    popal
    ret 4
bs_one:
    push dword ptr [esp + 0x28]
    push edi
    mov edx, dword ptr [edi]
    call dword ptr [edx + 8]
    ret

; --- dispatcher (0x10001000): effClose (1) of a plugin with an instance B closes B first and frees its panel record
poly_disp:
    cmp dword ptr [esp + 8], 1
    jne pd_go
    pushal
    call pd_base
pd_base:
    pop ebp
    sub ebp, pd_base
    mov eax, dword ptr [esp + 0x24]
    mov esi, dword ptr [eax + 0x40]
    lea ebx, [ebp + 0x10056ec0]
    mov edi, 4
pd_find:
    cmp dword ptr [ebx], esi
    jne pd_next
    cmp dword ptr [ebx + 4], 0
    je pd_free
    mov ecx, 12
    xor edx, edx
    call disp_b
    mov ecx, 1
    xor edx, edx
    call disp_b
    call close_ports
pd_free:
    mov dword ptr [ebx + 4], 0
    mov dword ptr [ebx + 8], 0
    mov dword ptr [ebx], 0                   ; last: the slot is free for other instances only now
pd_next:
    add ebx, 16
    dec edi
    jne pd_find
    mov eax, dword ptr [esi + 0xb0]          ; the panel record of A's engine (panel.asm) is free again
    lea ebx, [ebp + 0x10056f08]
    mov edi, 4
pd_rec:
    cmp dword ptr [ebx], eax
    jne pd_rnext
    mov dword ptr [ebx + 4], 0
    mov dword ptr [ebx + 8], 0
    mov dword ptr [ebx + 0xc], 0
    mov dword ptr [ebx], 0
pd_rnext:
    add ebx, 16
    dec edi
    jne pd_rec
    popal
pd_go:
    mov eax, dword ptr [esp + 4]
    push esi
    mov esi, dword ptr [eax + 0x40]
    jmp 0x10001008

; --- poly_count (stdcall this, op, ptr): the panel's POLYPHONY readout (0x100320A0) asks the settings object
;     (Get, vtable +0x20) for op 4 = voices in use; the voices in use of engine B are added. The settings object
;     is the engine object of plugin A ([A +0xB0]), which finds the slot.
poly_count:
    mov eax, dword ptr [esp + 4]
    mov ecx, dword ptr [eax]
    push dword ptr [esp + 0xc]
    push dword ptr [esp + 0xc]
    push eax
    call dword ptr [ecx + 0x20]
    cmp dword ptr [esp + 8], 4
    jne pc_ret
    pushal
    call pc_base
pc_base:
    pop ebp
    sub ebp, pc_base
    mov edx, dword ptr [esp + 0x24]
    lea ebx, [ebp + 0x10056ec0]
    mov edi, 4
pc_find:
    mov eax, dword ptr [ebx]
    test eax, eax
    je pc_next
    cmp edx, dword ptr [eax + 0xb0]
    jne pc_next
    mov eax, dword ptr [ebx + 4]
    test eax, eax
    je pc_out
    mov eax, dword ptr [eax + 0x40]
    mov eax, dword ptr [eax + 0xb0]
    mov eax, dword ptr [eax + 8]
    movzx ecx, word ptr [eax + 0x64c0]
    movzx eax, word ptr [eax + 0x64be]
    sub ecx, eax
    jbe pc_out
    mov eax, dword ptr [esp + 0x2c]
    add dword ptr [eax], ecx
    jmp pc_out
pc_next:
    add ebx, 16
    dec edi
    jne pc_find
pc_out:
    popal
pc_ret:
    ret 0xc
