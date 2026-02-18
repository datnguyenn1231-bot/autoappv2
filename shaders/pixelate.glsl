//!HOOK RGB
//!BIND HOOKED
//!DESC Pixel enlarge effect (GPU equivalent of FFmpeg scale=neighbor then lanczos)

vec4 hook() {
    // Pixelate: snap UV to a grid (simulates 2x upscale with nearest neighbor)
    vec2 uv = gl_FragCoord.xy / input_size;
    float pixelSize = 2.0;
    vec2 snapped = floor(uv * input_size / pixelSize) * pixelSize / input_size;

    return HOOKED_tex(snapped);
}
