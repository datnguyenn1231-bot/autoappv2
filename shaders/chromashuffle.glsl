//!HOOK RGB
//!BIND HOOKED
//!DESC Subtle channel mixing (GPU equivalent of FFmpeg colorchannelmixer)

vec4 hook() {
    vec4 c = HOOKED_texOff(0);

    // Matches: rr=0.98 rg=0.01 rb=0.01 gr=0.01 gg=0.98 gb=0.01 br=0.01 bg=0.01 bb=0.98
    vec3 mixed = vec3(
        c.r * 0.98 + c.g * 0.01 + c.b * 0.01,
        c.r * 0.01 + c.g * 0.98 + c.b * 0.01,
        c.r * 0.01 + c.g * 0.01 + c.b * 0.98
    );

    return vec4(mixed, 1.0);
}
