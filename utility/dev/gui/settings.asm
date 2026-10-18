; Settings page (dialog 111) of syxg50.dll: Send Reset buttons, MU Tone Map and the Output Level range.
; Code cave at 0x1002F6D3 (unused NOP block inside .text, no relocations), position independent (call/pop,
; ebp = load delta). Shared state with gui.asm in .data (see there): 0x10056E40 pending reset, 0x10056E58 queue.
; Controls: push buttons 0x42C MT-32, 0x423 GM, 0x424 GS, 0x425 XG, 0x42B GM2 ("Send Reset", issue #37): a click sends that
; reset once (pending for the audio thread); nothing is selected or saved. Radio buttons 0x427 Basic,
; 0x428 Native ("MU Tone Map" label 0x429, MU100 / MU128 / MU1000 only) drive the hidden checkbox 0x420 of the
; voice map patch (checked = MU Basic) and enable Apply; without a voice map appendix (0x10056DC1 != 1) they
; are hidden. The plugin state: getChunk / setChunk (vtable slots of both AudioEffect vtables, set in
; dllpatch.py) wrap the original functions and append 'R','P',skin,extra voices (4 bytes); the byte that held the
; Reset Mode of earlier versions now holds the panel skin (issue #52: 0 = none, 1 original, 2 Modern; skin_get /
; skin_set in poly/panel.asm).
; Output Level (trackbar 0x3FE): value 77-125 (101 = 0 dB, 0.5 dB steps, range set in dllpatch.py), tick at 101.

; --- page procedure (0x10030AF0, (page, hwnd, msg, wparam, lparam), ret 0x14) jumps here
dlg_hook:
    mov eax, dword ptr [esp + 0xc]
    cmp eax, 0x4e
    jne dh_cmd
    mov ecx, dword ptr [esp + 0x14]
    cmp dword ptr [ecx + 8], 0xffffff36
    jne dlg_orig
    call dh_base0
dh_base0:
    pop ecx
    sub ecx, dh_base0
    mov dl, byte ptr [ecx + 0x10056eb9]
    xor dl, 0x80
    mov byte ptr [ecx + 0x10056eb8], dl
    jmp dlg_reload
dh_cmd:
    cmp eax, 0x110
    je dh_after
    cmp eax, 0x111
    jne dlg_orig
    movzx eax, word ptr [esp + 0x10]
    cmp eax, 4
    je dh_after
    cmp eax, 0x42b
    je dh_btn
    cmp eax, 0x42c
    je dh_btn
    cmp eax, 0x423
    jb dlg_reload
    cmp eax, 0x428
    ja dlg_reload
dh_btn:
    cmp word ptr [esp + 0x12], 0
    jne dh_ret1
    pushal
    call dc_base
dc_base:
    pop ebp
    sub ebp, dc_base
    mov ebx, dword ptr [esp + 0x28]
    movzx eax, word ptr [esp + 0x30]
    cmp eax, 0x42c
    je dc_mt
    cmp eax, 0x42b
    je dc_gm2
    cmp eax, 0x426
    jae dc_tone
    sub eax, 0x422
    call send_reset
    popal
    jmp dh_ret1
dc_mt:
    mov eax, 5
    call send_reset
    popal
    jmp dh_ret1
dc_gm2:
    mov eax, 4
    call send_reset
    popal
    jmp dh_ret1
dc_tone:
    xor ecx, ecx
    cmp eax, 0x427
    sete cl
    push ecx
    push 0x420
    push ebx
    call dword ptr [ebp + 0x100401d0]
dc_end:
    push 0
    push ebx
    push 0x468
    push ebx
    call dword ptr [ebp + 0x10040170]
    push eax
    call dword ptr [ebp + 0x10040174]
    popal
dh_ret1:
    mov eax, 1
    ret 0x14
dlg_reload:
    mov eax, dword ptr [esp + 0xc]
dlg_orig:
    add eax, -0x4e
    jmp 0x10030af7

; WM_INITDIALOG / Set Defaults: the page's own code first, then the Utility controls
dh_after:
    push dword ptr [esp + 0x14]
    push dword ptr [esp + 0x14]
    push dword ptr [esp + 0x14]
    push dword ptr [esp + 0x14]
    push dword ptr [esp + 0x14]
    call dlg_call
    push eax
    pushal
    call da_base
da_base:
    pop ebp
    sub ebp, da_base
    mov ebx, dword ptr [esp + 0x2c]
    cmp dword ptr [esp + 0x30], 0x110
    jne da_defaults
    push 101
    push 0
    push 0x404
    push 0x3fe
    push ebx
    call dword ptr [ebp + 0x10040178]
    push eax
    call dword ptr [ebp + 0x10040174]
    mov al, byte ptr [ebp + 0x10056eb8]
    xor al, 0x80
    mov byte ptr [ebp + 0x10056eb9], al
    test al, al
    je da_sync
    movzx eax, al
    add eax, 128
    push eax
    push ebx
    call 0x10030ea0
    jmp da_sync
da_defaults:
    mov byte ptr [ebp + 0x10056eb9], 128
    push 256
    push ebx
    call 0x10030ea0
da_sync:
    cmp byte ptr [ebp + 0x10056dc1], 1
    jne da_hide
    push 0x420
    push ebx
    call get_check
    mov esi, eax
    push esi
    push 0x427
    push ebx
    call dword ptr [ebp + 0x100401d0]
    xor esi, 1
    push esi
    push 0x428
    push ebx
    call dword ptr [ebp + 0x100401d0]
    jmp da_end
da_hide:
    mov edi, 0x427
dh_loop:
    push edi
    push ebx
    call dword ptr [ebp + 0x10040178]
    push 0
    push eax
    call dword ptr [ebp + 0x100401b0]
    inc edi
    cmp edi, 0x42a
    jb dh_loop
da_end:
    popal
    pop eax
    ret 0x14
dlg_call:
    mov eax, dword ptr [esp + 0xc]
    add eax, -0x4e
    jmp 0x10030af7

; get_check(hwnd, id) -> eax = BM_GETCHECK of the control (stdcall)
get_check:
    push dword ptr [esp + 8]
    push dword ptr [esp + 8]
    call dword ptr [ebp + 0x10040178]
    push 0
    push 0
    push 0xf0
    push eax
    call dword ptr [ebp + 0x10040174]
    and eax, 1
    ret 8

; send_reset: eax = reset (1 GM, 2 GS, 3 XG, 4 GM2) -> pending, sent once by the audio thread (event queue on
; first use)
send_reset:
    push eax
    cmp dword ptr [ebp + 0x10056e58], 0
    jne sm_have
    push 4
    push 0x3000
    push 0x10000
    push 0
    call dword ptr [ebp + 0x1004013c]
    mov dword ptr [ebp + 0x10056e58], eax
sm_have:
    pop eax
    mov byte ptr [ebp + 0x10056e40], al
    ret

; --- Output Level trackbar, WM_HSCROLL (0x10031142, eax = value byte, ebx = page): keep 77-125, then show it
lvl_clamp:
    mov cl, byte ptr [eax]
    cmp cl, 77
    jae lc_hi
    mov cl, 77
lc_hi:
    cmp cl, 125
    jbe lc_set
    mov cl, 125
lc_set:
    mov byte ptr [eax], cl
    movzx ecx, cl
    push ecx
    push ebx
    call 0x100311b0
    jmp 0x1003114c

; --- Polyphony trackbar (0x3F9), WM_HSCROLL (0x10030F31; page hwnd ebx, wParam [esp+0x14], trackbar [esp+0x1c],
;     settings byte pointer [esp+0x20]): range 8-256 (TBM_SETRANGE in dllpatch.py); the trackbar position is the
;     total, the settings byte keeps up to 128, the rest goes to the extra voices on the page (0x10056EB9)
poly_scroll:
    movzx eax, word ptr [esp + 0x14]
    cmp eax, 7
    ja 0x10031162
    call ps_base0
ps_base0:
    pop ecx
    sub ecx, ps_base0
    push 0
    push 0
    push 0x400
    push dword ptr [esp + 0x28]
    call dword ptr [ecx + 0x10040174]
    cmp eax, 8
    jge ps_lo
    mov eax, 8
ps_lo:
    cmp eax, 256
    jle ps_hi
    mov eax, 256
ps_hi:
    call ps_base
ps_base:
    pop ecx
    sub ecx, ps_base
    mov edx, eax
    sub edx, 128
    jg ps_extra
    xor edx, edx
ps_extra:
    mov byte ptr [ecx + 0x10056eb9], dl
    mov edx, eax
    cmp edx, 128
    jle ps_byte
    mov edx, 128
ps_byte:
    mov ecx, dword ptr [esp + 0x20]
    mov byte ptr [ecx], dl
    push eax
    push ebx
    call 0x10030ea0
    jmp 0x1003114c

; --- getChunk (thiscall: void **data, bool isPreset; ret 8): original chunk + 'R','P',skin,extra voices
chunk_get:
    push dword ptr [esp + 8]
    push dword ptr [esp + 8]
    call 0x10002b50
    pushal
    call cg_base
cg_base:
    pop ebp
    sub ebp, cg_base
    mov ecx, eax
    cmp ecx, 0x40
    ja cg_out
    mov edx, dword ptr [esp + 0x24]
    mov esi, dword ptr [edx]
    lea edi, [ebp + 0x10056e70]
    mov dword ptr [edx], edi
    rep movsb
    mov word ptr [edi], 0x5052
    push eax
    call SKIN_GET                            ; byte 2: the panel skin (issue #52), 1 original / 2 Modern
    mov byte ptr [edi + 2], al
    pop eax
    mov cl, byte ptr [ebp + 0x10056eb8]
    xor cl, 0x80
    mov byte ptr [edi + 3], cl
    add eax, 4
    mov dword ptr [esp + 0x1c], eax
cg_out:
    popal
    ret 8

; --- setChunk (thiscall: void *data, int size, bool isPreset; ret 0xc): takes 'R','S' / 'R','P',x,extra off the
;     end (the Reset Mode byte of earlier versions is ignored, no reset is sent)
chunk_set:
    pushal
    call cs_base
cs_base:
    pop ebp
    sub ebp, cs_base
    mov eax, dword ptr [esp + 0x28]
    cmp eax, 9
    jb cs_out
    mov esi, dword ptr [esp + 0x24]
    mov ecx, 128
    cmp word ptr [esi + eax - 4], 0x5352
    je cs_tag
    cmp word ptr [esi + eax - 4], 0x5052
    jne cs_out
    push eax
    mov al, byte ptr [esi + eax - 2]         ; the panel skin (0 = none: the ini decides)
    call SKIN_SET
    pop eax
    mov cl, byte ptr [esi + eax - 1]
    cmp cl, 128
    jbe cs_tag
    mov cl, 128
cs_tag:
    xor cl, 0x80
    mov byte ptr [ebp + 0x10056eb8], cl
    sub dword ptr [esp + 0x28], 4
cs_out:
    popal
    jmp 0x10002bb0
