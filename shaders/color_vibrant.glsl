//!HOOK RGB
//!BIND HOOKED
//!DESC Vibrant color grading (GPU equivalent of FFmpeg vibrant preset)

vec4 hook() {
    vec4 c = HOOKED_texOff(0);

    // eq=brightness=0.15:contrast=1.08:saturation=1.22
    c.rgb += 0.15;
    c.rgb = (c.rgb - 0.5) * 1.08 + 0.5;
    float luma = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    c.rgb = mix(vec3(luma), c.rgb, 1.22);

    // vibrance=intensity=0.15 (boost low-saturation colors more)
    float maxC = max(c.r, max(c.g, c.b));
    float minC = min(c.r, min(c.g, c.b));
    float sat = (maxC - minC) / (maxC + 0.001);
    float boost = 1.0 + 0.15 * (1.0 - sat);
    c.rgb = mix(vec3(luma), c.rgb, boost);

    // curves: slight midtone lift (0.5 → 0.55)
    c.rgb = pow(c.rgb, vec3(0.92));

    // unsharp=5:5:0.8 (mild sharpen)
    vec4 blur = vec4(0.0);
    float w = 0.0;
    for (int x = -2; x <= 2; x++) {
        for (int y = -2; y <= 2; y++) {
            float g = exp(-float(x*x + y*y) / 4.5);
            blur += HOOKED_texOff(vec2(float(x), float(y))) * g;
            w += g;
        }
    }
    blur /= w;
    c.rgb += (c.rgb - blur.rgb) * 0.8;

    return clamp(c, 0.0, 1.0);
}
