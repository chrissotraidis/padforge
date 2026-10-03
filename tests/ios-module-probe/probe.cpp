// The universal iPhone module probe: uses one of the app's exports and the device's
// C and C++ libraries. No game code.
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

extern "C" std::uint64_t SDL_GetTicks(void);  // exported by the published KartPad app

extern "C" __attribute__((visibility("default"))) double padmint_module_probe(int count) {
    std::vector<double> values(static_cast<std::size_t>(count));
    for (int i = 0; i < count; ++i) values[static_cast<std::size_t>(i)] = std::sqrt(static_cast<double>(i));
    std::string label = "padmint";
    return values.empty() ? 0.0 : values.back() + static_cast<double>(label.size() + SDL_GetTicks() * 0);
}
