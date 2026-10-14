; ini settings (issue #36), part of section .sxp (assembled after poly.asm and panel.asm). The DLL reads
; <dll name>.ini through two helpers: 0x100330FC (int: section, key, default; GetPrivateProfileIntA) and
; 0x1003311C (string: section, key, default, buffer, size; GetPrivateProfileStringA), path at 0x10056B98.
; They jump here. Each key is looked up in the sections [Config] (SXG-Create, kept), [SYXG50] (the original
; S-YXG50 name; Falcosoft's VST MIDI Driver and MIDI Player write DebugPanel there to switch the debug panel)
; and [<plugin id>] (dll name without .dll in capitals, e.g. SYXG100; written by the converter, ini_id is set
; per model by dllpatch.py), the first one that has it wins. The table is VoiceTable= (original) or SoftSynth=.

ini_int:
    push ecx
    push edx
    push ebx
    push esi
    push edi
    push ebp
    call ii_base
ii_base:
    pop ebp
    sub ebp, ii_base
    mov edi, dword ptr [esp + 0x20]          ; key
    xor esi, esi
ii_loop:
    call ini_section                         ; esi = 0, 1, 2 -> eax = section name
    test eax, eax
    je ii_default
    lea ecx, [ebp + 0x10056b98]
    push ecx
    push 0x7ffeabcd                          ; "missing"
    push edi
    push eax
    call dword ptr [ebp + 0x100400b8]
    cmp eax, 0x7ffeabcd
    jne ii_ret
    inc esi
    jmp ii_loop
ii_default:
    mov eax, dword ptr [esp + 0x24]
ii_ret:
    pop ebp
    pop edi
    pop esi
    pop ebx
    pop edx
    pop ecx
    ret 0xc

ini_str:
    push ecx
    push edx
    push ebx
    push esi
    push edi
    push ebp
    call is_base
is_base:
    pop ebp
    sub ebp, is_base
    xor esi, esi
is_loop:
    call ini_section
    test eax, eax
    je is_default
    mov ebx, eax
    mov edi, dword ptr [esp + 0x20]          ; key as asked
    call is_try
    jne is_ret
    mov eax, dword ptr [esp + 0x20]          ; the table key: also SoftSynth=
    lea ecx, [ebp + 0x100519f4]
    cmp eax, ecx
    jne is_next
    lea edi, [ebp + key_softsynth]
    call is_try
    jne is_ret
is_next:
    inc esi
    jmp is_loop
is_default:
    lea ecx, [ebp + 0x10056b98]
    push ecx
    push dword ptr [esp + 0x30]              ; size
    push dword ptr [esp + 0x30]              ; buffer
    push dword ptr [esp + 0x30]              ; default
    push dword ptr [esp + 0x30]              ; key
    lea eax, [ebp + sec_config]
    push eax
    call dword ptr [ebp + 0x10040038]
is_ret:
    pop ebp
    pop edi
    pop esi
    pop ebx
    pop edx
    pop ecx
    ret 0x14
; is_try: section ebx, key edi -> eax = length, ZF clear (jne) if the key is there
is_try:
    lea ecx, [ebp + 0x10056b98]
    push ecx
    push dword ptr [esp + 0x34]              ; size
    push dword ptr [esp + 0x34]              ; buffer
    lea ecx, [ebp + str_missing]
    push ecx
    push edi
    push ebx
    call dword ptr [ebp + 0x10040038]
    mov ecx, dword ptr [esp + 0x2c]          ; buffer
    cmp byte ptr [ecx], 1
    jne it_found
    cmp eax, eax
    ret
it_found:
    or esp, esp
    ret
; ini_section: esi = 0 / 1 / 2 -> eax = "Config" / "SYXG50" / ini_id (0 when done or ini_id empty)
ini_section:
    lea eax, [ebp + sec_config]
    cmp esi, 0
    je sc_ret
    lea eax, [ebp + 0x100519ec]
    cmp esi, 1
    je sc_ret
    lea eax, [ebp + ini_id]
    cmp esi, 2
    jne sc_none
    cmp byte ptr [eax], 0
    jne sc_ret
sc_none:
    xor eax, eax
sc_ret:
    ret

sec_config:
    .ascii "Config"
    .byte 0
key_softsynth:
    .ascii "SoftSynth"
    .byte 0
str_missing:
    .byte 1, 0
; ini_id: the plugin's own section name (16 bytes, set per model by dllpatch.py)
ini_id:
    .byte 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
