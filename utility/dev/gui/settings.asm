; Settings page (dialog 111) of syxg50.dll: "Utility" box and the Output Level range.
; Code cave at 0x1002F6D3 (unused NOP block inside .text, no relocations), position independent (call/pop,
; ebp = load delta). Shared state with gui.asm in .data (see there): 0x10056E40 pending reset,
; 0x10056E41 Reset Mode XOR 3, 0x10056E58 event queue, 0x10056E64 "Enable SysEx in files", 0x10056E68 EnableWindow.
; Controls: radio buttons 0x422 None, 0x423 GM, 0x424 GS, 0x425 XG ("Reset Mode" label 0x42A), checkbox 0x426
; "Enable SysEx in files" (greys the Reset Mode out while on), radio buttons 0x427 Basic, 0x428 Native
; ("MU Tone Map" label 0x429, MU100 / MU128 / MU1000 only). The tone map radios drive the hidden checkbox
; 0x420 of the voice map patch (checked = MU Basic), so its WM_INITDIALOG / Set Defaults / PSN_APPLY code
; stays as it is; without a voice map appendix (0x10056DC1 != 1) they are hidden.
; Output Level (trackbar 0x3FE): value 77-125 (101 = 0 dB, 0.5 dB steps, range set in dllpatch.py), tick at 101.

; --- page procedure (0x10030AF0, (page, hwnd, msg, wparam, lparam), ret 0x14) jumps here
dlg_hook:
    mov eax, dword ptr [esp + 0xc]
    cmp eax, 0x110
    je dh_after
    cmp eax, 0x111
    jne dlg_orig
    movzx eax, word ptr [esp + 0x10]
    cmp eax, 4
    je dh_after
    cmp eax, 0x422
    jb dlg_reload
    cmp eax, 0x428
    ja dlg_reload
    cmp word ptr [esp + 0x12], 0
    jne dh_ret1
    pushal
    call dc_base
dc_base:
    pop ebp
    sub ebp, dc_base
    mov ebx, dword ptr [esp + 0x28]
    movzx eax, word ptr [esp + 0x30]
    cmp eax, 0x426
    je dc_sysex
    ja dc_tone
    sub eax, 0x422
    mov ecx, eax
    xor cl, 3
    mov byte ptr [ebp + 0x10056e41], cl
    test eax, eax
    jne dc_pend
    mov al, 5
dc_pend:
    push eax
    cmp dword ptr [ebp + 0x10056e58], 0
    jne dc_have
    push 4
    push 0x3000
    push 0x10000
    push 0
    call dword ptr [ebp + 0x1004013c]
    mov dword ptr [ebp + 0x10056e58], eax
dc_have:
    pop eax
    mov byte ptr [ebp + 0x10056e40], al
    jmp dc_end
dc_sysex:
    push 0x426
    push ebx
    call get_check
    mov byte ptr [ebp + 0x10056e64], al
    call enable_reset
    jmp dc_end
dc_tone:
    xor ecx, ecx
    cmp eax, 0x427
    sete cl
    push ecx
    push 0x420
    push ebx
    call dword ptr [ebp + 0x100401d0]
    push 0
    push ebx
    push 0x468
    push ebx
    call dword ptr [ebp + 0x10040170]
    push eax
    call dword ptr [ebp + 0x10040174]
dc_end:
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
    jmp da_sync
da_defaults:
    mov byte ptr [ebp + 0x10056e41], 0
    mov byte ptr [ebp + 0x10056e64], 0
da_sync:
    movzx esi, byte ptr [ebp + 0x10056e41]
    xor esi, 3
    add esi, 0x422
    mov edi, 0x422
ds_loop:
    xor eax, eax
    cmp edi, esi
    sete al
    push eax
    push edi
    push ebx
    call dword ptr [ebp + 0x100401d0]
    inc edi
    cmp edi, 0x426
    jb ds_loop
    movzx eax, byte ptr [ebp + 0x10056e64]
    push eax
    push 0x426
    push ebx
    call dword ptr [ebp + 0x100401d0]
    call enable_reset
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

; enable_reset (ebx = page): Reset Mode radios and label enabled unless "Enable SysEx in files" is on
enable_reset:
    mov eax, dword ptr [ebp + 0x10056e68]
    test eax, eax
    jne er_have
    lea eax, [ebp + txt_user32]
    push eax
    call dword ptr [ebp + 0x10040104]
    test eax, eax
    je er_ret
    lea ecx, [ebp + txt_enable]
    push ecx
    push eax
    call dword ptr [ebp + 0x10040030]
    mov dword ptr [ebp + 0x10056e68], eax
    test eax, eax
    je er_ret
er_have:
    push esi
    push edi
    mov esi, eax
    mov edi, 0x422
er_loop:
    push edi
    push ebx
    call dword ptr [ebp + 0x10040178]
    xor ecx, ecx
    cmp byte ptr [ebp + 0x10056e64], 0
    sete cl
    push ecx
    push eax
    call esi
    inc edi
    cmp edi, 0x426
    jb er_loop
    jne er_done
    mov edi, 0x42a
    jmp er_loop
er_done:
    pop edi
    pop esi
er_ret:
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

txt_user32:
    .ascii "USER32.dll"
    .byte 0
txt_enable:
    .ascii "EnableWindow"
    .byte 0
