; GS / XG reset from the Settings page (dialog 111, combo box 0x421), syxg50.dll
; Code cave at 0x1003FA80, position independent (call/pop, ebp = load delta). State in .data:
;   0x10056E40  pending reset (0 = none, 1 = GS, 2 = XG), set by the dialog, taken by the audio thread
;   0x10056E41  combo box selection (0 = GS, 1 = XG), restored when the page is opened again
; The SysEx goes through the same entry as a host SysEx event (engine = plugin +0xB0, vtable +0x0C,
; stdcall (engine, data, length)), at the start of the next process / processReplacing call.

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
    movzx eax, byte ptr [ebp + 0x10056e40]
    test eax, eax
    je sp_done
    mov byte ptr [ebp + 0x10056e40], 0
    mov edx, dword ptr [esp + 0x28]
    mov ecx, dword ptr [edx + 0x40]
    mov ecx, dword ptr [ecx + 0xb0]
    test ecx, ecx
    je sp_done
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
sp_done:
    popal
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
