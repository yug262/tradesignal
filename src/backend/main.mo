import Map "mo:core/Map";
import Types "types/trading";
import ConfigEngine "lib/config_engine";
import ProcessingStateLib "lib/processing_state";
import NewsApi "mixins/news-api";
import ConfigApi "mixins/config-api";
import DashboardApi "mixins/dashboard-api";

actor {

  // ─── Stable state ──────────────────────────────────────────────────────────

  let news_store = Map.empty<Text, Types.NewsArticleRef>();

  var config = { var data : Types.SystemConfig = ConfigEngine.default_config() };

  var proc_state = {
    var data : Types.ProcessingState = ProcessingStateLib.default_state()
  };

  // ─── Mixin composition ─────────────────────────────────────────────────────

  include NewsApi(news_store, config, proc_state);
  include ConfigApi(config);
  include DashboardApi(news_store, config, proc_state);

};
