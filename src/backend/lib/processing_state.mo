import Types "../types/trading";

module {

  // Return the default (zero) processing state.
  public func default_state() : Types.ProcessingState {
    {
      last_processed_article_id = null;
      last_poll_timestamp       = 0;
      total_articles_processed  = 0;
      current_mode              = "pre_market";
      is_polling_active         = false;
      articles_in_queue         = 0;
    }
  };

  // Return an updated state after marking an article as processed.
  public func mark_processed(
    state      : Types.ProcessingState,
    article_id : Text,
    now        : Int,
  ) : Types.ProcessingState {
    {
      state with
      last_processed_article_id = ?article_id;
      last_poll_timestamp       = now;
      total_articles_processed  = state.total_articles_processed + 1;
    }
  };

  // Return a freshly zeroed state with last_poll_timestamp set to now.
  public func reset(now : Int) : Types.ProcessingState {
    { default_state() with last_poll_timestamp = now }
  };

};
