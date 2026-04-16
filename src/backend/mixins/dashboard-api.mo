import Map "mo:core/Map";
import Iter "mo:core/Iter";
import Types "../types/trading";

mixin (
  news_store : Map.Map<Text, Types.NewsArticleRef>,
  config     : { var data : Types.SystemConfig },
  proc_state : { var data : Types.ProcessingState },
) {

  // Return aggregated dashboard summary across all state slices.
  public func get_dashboard_summary() : async Types.DashboardSummary {
    let total = news_store.size();

    // 24 hours in nanoseconds
    let h24_ns : Int = 86_400_000_000_000;
    let now_approx : Int = 1_713_225_600_000_000_000;

    var processed_today : Nat = 0;
    var pending_count   : Nat = 0;

    for (art in news_store.values()) {
      if (art.analyzed_at >= now_approx - h24_ns) {
        processed_today += 1;
      };
      if (art.processing_status == "pending") {
        pending_count += 1;
      };
    };

    let endpoint_status = if (config.data.use_mock_data) "mock" else "live";

    {
      total_articles_consumed  = total;
      articles_processed_today = processed_today;
      pending_candidates       = pending_count;
      active_opportunities     = 0;   // Phase 2
      no_trade_count           = 0;   // Phase 2
      system_mode              = config.data.processing_mode;
      last_refresh             = proc_state.data.last_poll_timestamp;
      endpoint_status          = endpoint_status;
    }
  };

  // Return current processing state.
  public func get_processing_state() : async Types.ProcessingState {
    proc_state.data
  };

};
