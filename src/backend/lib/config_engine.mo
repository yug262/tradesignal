import Types "../types/trading";

module {

  // Return the default system configuration.
  public func default_config() : Types.SystemConfig {
    {
      capital               = 100_000.0;
      risk_per_trade_pct    = 1.0;
      max_open_positions    = 5;
      max_daily_loss_pct    = 3.0;
      min_rr                = 1.5;
      news_endpoint_url     = "https://api.example.com/news";
      polling_interval_mins = 5;
      use_mock_data         = true;
      processing_mode       = "pre_market";
    }
  };

  // Validate and apply a new config; returns true when all rules pass.
  // Rules:
  //   capital > 0
  //   risk_per_trade_pct in [0.5, 5.0]
  //   min_rr >= 1.0
  //   max_open_positions in [1, 20]
  //   polling_interval_mins >= 1
  public func validate_config(config : Types.SystemConfig) : Bool {
    if (config.capital <= 0.0) return false;
    if (config.risk_per_trade_pct < 0.5 or config.risk_per_trade_pct > 5.0) return false;
    if (config.min_rr < 1.0) return false;
    if (config.max_open_positions < 1 or config.max_open_positions > 20) return false;
    if (config.polling_interval_mins < 1) return false;
    true
  };

};
