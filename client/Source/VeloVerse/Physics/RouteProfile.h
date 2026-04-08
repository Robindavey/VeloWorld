#pragma once

#include "VeloVerse/Physics/ForceModel.h"

#include <string>
#include <vector>

namespace VeloVerse::Physics {

class RouteProfile {
public:
    bool LoadFromJsonFile(const std::string& path);

    RouteAttributes GetAttributesAtPosition(float positionM) const;

    float GetTotalLengthM() const { return static_cast<float>(m_attributes.size()); }

    // Helper for tests and in-memory construction
    void SetAttributesForTesting(const std::vector<RouteAttributes>& attrs) { m_attributes = attrs; }

private:
    std::vector<RouteAttributes> m_attributes;
};

} // namespace VeloVerse::Physics

