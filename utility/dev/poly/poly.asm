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
    jle pm_done
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
    jmp pm_done
pm_idle:
    mov eax, dword ptr [esp + 0x30]
    sub dword ptr [ebx + 8], eax
    jg pm_done
    mov dword ptr [ebx + 8], 0
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
    push 0x4000
    push 0
    call dword ptr [ebp + 0x1004013c]
    test eax, eax
    je cb_ret
    mov dword ptr [ebx + 0xc], eax
cb_main:
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
    mov eax, dword ptr [ebx + 4]
    mov edi, dword ptr [eax + 0x40]
    mov eax, dword ptr [esi + 0xd8]
    cmp eax, dword ptr [edi + 0xd8]
    je sb_set
    push edi
    call set_rate
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

; --- dispatcher (0x10001000): effClose (1) of a plugin with an instance B closes B first
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
pd_free:
    mov dword ptr [ebx + 4], 0
    mov dword ptr [ebx + 8], 0
    mov dword ptr [ebx], 0                   ; last: the slot is free for other instances only now
pd_next:
    add ebx, 16
    dec edi
    jne pd_find
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
