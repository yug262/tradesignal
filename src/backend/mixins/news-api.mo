import Map "mo:core/Map";
import Types "../types/trading";
import NewsConsumer "../lib/news_consumer";

mixin (
  news_store : Map.Map<Text, Types.NewsArticleRef>,
  config     : { var data : Types.SystemConfig },
  proc_state : { var data : Types.ProcessingState },
) {

  // Return a paginated list of all stored news articles.
  public func get_news(page : Nat, page_size : Nat) : async [Types.NewsArticleRef] {
    NewsConsumer.get_all_news(news_store, page, page_size)
  };

  // Lookup a single article by id.
  public func get_news_by_id(id : Text) : async ?Types.NewsArticleRef {
    NewsConsumer.get_news_by_id(news_store, id)
  };

  // Return articles filtered by optional symbol, category, and min impact.
  public func filter_news(
    symbol     : ?Text,
    category   : ?Text,
    min_impact : ?Float,
  ) : async [Types.NewsArticleRef] {
    NewsConsumer.filter_news(news_store, symbol, category, min_impact)
  };

  // Trigger a news fetch (loads mock data or returns live-endpoint placeholder).
  public func fetch_news() : async Text {
    if (config.data.use_mock_data) {
      NewsConsumer.load_mock_data(news_store)
    } else {
      "Live endpoint not configured"
    }
  };

  // Return total count of stored articles.
  public func get_total_news_count() : async Nat {
    NewsConsumer.get_total_count(news_store)
  };

};
