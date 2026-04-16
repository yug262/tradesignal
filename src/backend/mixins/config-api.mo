import Types "../types/trading";
import ConfigEngine "../lib/config_engine";

mixin (config : { var data : Types.SystemConfig }) {

  // Return current system configuration.
  public func get_config() : async Types.SystemConfig {
    config.data
  };

  // Replace configuration; returns true on success, false when validation fails.
  public func update_config(cfg : Types.SystemConfig) : async Bool {
    if (ConfigEngine.validate_config(cfg)) {
      config.data := cfg;
      true
    } else {
      false
    }
  };

  // Reset configuration to factory defaults and return the default config.
  public func reset_config() : async Types.SystemConfig {
    let defaults = ConfigEngine.default_config();
    config.data := defaults;
    defaults
  };

};
