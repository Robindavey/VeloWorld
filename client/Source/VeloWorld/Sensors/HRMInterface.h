#pragma once

namespace VeloWorld::Sensors {

class HRMInterface {
public:
    virtual ~HRMInterface() = default;

    virtual bool Connect() = 0;
    virtual void Disconnect() = 0;
    virtual bool IsConnected() const = 0;

    virtual int GetHeartRateBPM() const = 0;
};

} // namespace VeloWorld::Sensors