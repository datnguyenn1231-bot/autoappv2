//!HOOK RGB
//!BIND HOOKED
//!DESC Glow/Bloom effect (GPU equivalent of FFmpeg split+gblur=sigma=3.5+blend=screen:0.18)

vec4 hook() {
    vec4 original = HOOKED_texOff(0);

    // Gaussian blur approximation (5x5 kernel, sigma ≈ 3.5)
    vec4 blur = vec4(0.0);
    float totalWeight = 0.0;

    for (int x = -4; x <= 4; x++) {
        for (int y = -4; y <= 4; y++) {
            float dist = float(x * x + y * y);
            float weight = exp(-dist / (2.0 * 3.5 * 3.5));
            blur += HOOKED_texOff(vec2(float(x), float(y))) * weight;
            totalWeight += weight;
        }
    }
    blur /= totalWeight;

    // Screen blend: result = a + b - a*b, with opacity 0.18
    vec4 blended = original + blur * 0.18 - original * blur * 0.18;

    return clamp(blended, 0.0, 1.0);
}
