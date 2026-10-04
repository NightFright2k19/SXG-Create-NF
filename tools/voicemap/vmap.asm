
vm_init:
    mov eax, dword ptr [esp+4]
    push eax
    call 0x100043d0
    pushad
    call d1
d1: pop ebp
    sub ebp, d1
    mov esi, dword ptr [esp+0x24]
    xor eax, eax
    lea edi, [esi+0x20]
    mov ecx, 17
s1: add eax, dword ptr [edi]
    add edi, 4
    loop s1
    lea edi, [esi+eax+0x64]
    mov byte ptr [ebp+0x10056dc1], 0
    cmp dword ptr [edi], 0x3250414d
    jne i_out
    mov dword ptr [ebp+0x10056dc4], edi
    mov eax, dword ptr [ebp+0x100552d0]
    mov dword ptr [ebp+0x10056dc8], eax
    mov eax, dword ptr [ebp+0x100552cc]
    mov dword ptr [ebp+0x10056dcc], eax
    mov eax, dword ptr [ebp+0x100552f8]
    mov dword ptr [ebp+0x10056dd0], eax
    mov eax, dword ptr [ebp+0x100552e8]
    mov dword ptr [ebp+0x10056dd4], eax
    mov eax, dword ptr [ebp+0x100552d8]
    mov dword ptr [ebp+0x10056dd8], eax
    mov eax, dword ptr [ebp+0x100552d4]
    mov dword ptr [ebp+0x10056ddc], eax
    mov eax, dword ptr [ebp+0x100552e4]
    mov dword ptr [ebp+0x10056de0], eax
    mov eax, dword ptr [ebp+0x100552e0]
    mov dword ptr [ebp+0x10056de4], eax
    mov byte ptr [ebp+0x10056dc1], 1
    movzx eax, byte ptr [edi+4]
    push eax
    lea eax, [ebp+@key@]
    push eax
    lea eax, [ebp+0x100519ec]
    push eax
    call 0x100330fc
    test eax, eax
    setne al
    mov byte ptr [ebp+0x10056dc0], al
    call @vm_apply@
i_out:
    popad
    ret 4

vm_apply:
    pushad
    call d2
d2: pop ebp
    sub ebp, d2
    cmp byte ptr [ebp+0x10056dc1], 1
    jne a_out
    cmp byte ptr [ebp+0x10056dc0], 0
    je a_nat
    mov esi, dword ptr [ebp+0x10056dc4]
    lea eax, [esi+0x8]
    mov dword ptr [ebp+0x100552d0], eax
    lea eax, [esi+0x88]
    mov dword ptr [ebp+0x100552cc], eax
    lea eax, [esi+0x108]
    mov dword ptr [ebp+0x100552f8], eax
    lea eax, [esi+0x188]
    mov dword ptr [ebp+0x100552e8], eax
    lea eax, [esi+0x208]
    mov dword ptr [ebp+0x100552d8], eax
    lea eax, [esi+0x288]
    mov dword ptr [ebp+0x100552d4], eax
    lea eax, [esi+0x308]
    mov dword ptr [ebp+0x100552e4], eax
    lea eax, [esi+0x388]
    mov dword ptr [ebp+0x100552e0], eax
    jmp a_out
a_nat:
    mov eax, dword ptr [ebp+0x10056dc8]
    mov dword ptr [ebp+0x100552d0], eax
    mov eax, dword ptr [ebp+0x10056dcc]
    mov dword ptr [ebp+0x100552cc], eax
    mov eax, dword ptr [ebp+0x10056dd0]
    mov dword ptr [ebp+0x100552f8], eax
    mov eax, dword ptr [ebp+0x10056dd4]
    mov dword ptr [ebp+0x100552e8], eax
    mov eax, dword ptr [ebp+0x10056dd8]
    mov dword ptr [ebp+0x100552d8], eax
    mov eax, dword ptr [ebp+0x10056ddc]
    mov dword ptr [ebp+0x100552d4], eax
    mov eax, dword ptr [ebp+0x10056de0]
    mov dword ptr [ebp+0x100552e4], eax
    mov eax, dword ptr [ebp+0x10056de4]
    mov dword ptr [ebp+0x100552e0], eax
a_out:
    popad
    ret

vm_save:
    pushad
    call d3
d3: pop ebp
    sub ebp, d3
    lea eax, [ebp+@k32@]
    push eax
    call dword ptr [ebp+0x10040104]
    test eax, eax
    je v_out
    lea ecx, [ebp+@wpps@]
    push ecx
    push eax
    call dword ptr [ebp+0x10040030]
    test eax, eax
    je v_out
    lea ecx, [ebp+0x10056b98]
    push ecx
    lea ecx, [ebp+@s0@]
    cmp byte ptr [ebp+0x10056dc0], 0
    je v1
    lea ecx, [ebp+@s1t@]
v1: push ecx
    lea ecx, [ebp+@key@]
    push ecx
    lea ecx, [ebp+0x100519ec]
    push ecx
    call eax
v_out:
    popad
    ret

dlg_init:
    xor eax, eax
    jmp dlg_common
dlg_default:
    mov eax, 1
dlg_common:
    push eax
    push dword ptr [esp+0xc]
    push dword ptr [esp+0xc]
    call 0x10031200
    pop eax
    pushad
    call d4
d4: pop ebp
    sub ebp, d4
    mov ebx, dword ptr [esp+0x24]
    mov edi, eax
    push 0x420
    push ebx
    call dword ptr [ebp+0x10040178]
    cmp byte ptr [ebp+0x10056dc1], 1
    je g_vis
    push 0
    push eax
    call dword ptr [ebp+0x100401b0]
    jmp g_out
g_vis:
    movzx eax, byte ptr [ebp+0x10056dc0]
    test edi, edi
    je g_set
    mov ecx, dword ptr [ebp+0x10056dc4]
    movzx eax, byte ptr [ecx+4]
g_set:
    push eax
    push 0x420
    push ebx
    call dword ptr [ebp+0x100401d0]
g_out:
    popad
    ret 8

cmd_hook:
    movzx eax, word ptr [esp+0x14]
    mov esi, dword ptr [esp+0xc]
    cmp eax, 0x420
    jne c_n
    jmp 0x10030d21
c_n:
    cmp eax, 0x3f6
    jmp 0x10030bfd

apply_hook:
    pushad
    call d5
d5: pop ebp
    sub ebp, d5
    cmp byte ptr [ebp+0x10056dc1], 1
    jne h_out
    mov ebx, dword ptr [esp+0x2c]
    push 0x420
    push ebx
    call dword ptr [ebp+0x10040178]
    push 0
    push 0
    push 0xf0
    push eax
    call dword ptr [ebp+0x10040174]
    cmp eax, 1
    sete al
    cmp al, byte ptr [ebp+0x10056dc0]
    je h_out
    mov byte ptr [ebp+0x10056dc0], al
    call @vm_apply@
    call @vm_save@
h_out:
    popad
    mov ecx, dword ptr [esp+8]
    mov eax, dword ptr [ecx+8]
    jmp 0x10030bc1

key:  .byte 0x4d,0x55,0x42,0x61,0x73,0x69,0x63,0
k32:  .byte 0x4b,0x45,0x52,0x4e,0x45,0x4c,0x33,0x32,0x2e,0x44,0x4c,0x4c,0
wpps: .byte 0x57,0x72,0x69,0x74,0x65,0x50,0x72,0x69,0x76,0x61,0x74,0x65,0x50,0x72,0x6f,0x66,0x69,0x6c,0x65,0x53,0x74,0x72,0x69,0x6e,0x67,0x41,0
s0:   .byte 0x30,0
s1t:  .byte 0x31,0
