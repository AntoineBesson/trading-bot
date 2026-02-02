from abc import ABC, abstractmethod
import pandas as pd
import numpy as np

class PrimaryModel(ABC):
    """
    Abstract Base Class for Primary Models.
    A Primary Model is responsible for generating the initial entry signals (Side).
    """
    
    @abstractmethod
    def generate_signals(self, prices: pd.Series) -> pd.DataFrame:
        """
        Generates trading signals based on prices.
        
        Args:
            prices (pd.Series): A series of prices (e.g., Dollar Bars Close).
            
        Returns:
            pd.DataFrame: A DataFrame with the same index as prices, containing:
                          - 'signal': The side of the bet (1 for Long, -1 for Short, 0 for None).
                          - 't_events': Timestamps of the signals.
        """
        pass

class MovingAverageCrossover(PrimaryModel):
    """
    A simple primary model that generates signals based on MA crossover.
    """
    def __init__(self, fast_window=10, slow_window=50):
        self.fast_window = fast_window
        self.slow_window = slow_window
        
    def generate_signals(self, prices: pd.Series) -> pd.DataFrame:
        # Calculate MAs
        fast_ma = prices.rolling(window=self.fast_window).mean()
        slow_ma = prices.rolling(window=self.slow_window).mean()
        
        # Signal: Fast > Slow = Long (1), Fast < Slow = Short (-1)
        raw_signal = np.where(fast_ma > slow_ma, 1, -1)
        
        # We want to efficiently capture the *change* in signal (the crossover event)
        # Shift signal by 1 to compare with previous
        prev_signal = np.roll(raw_signal, 1)
        
        # Create timestamps where signal changed
        # We start from index slow_window because before that MAs are NaN
        # Also, we explicitly want the moment the cross happens.
        
        # A change happens when raw_signal != prev_signal
        # (and ignore the first few NaNs)
        
        # Let's put it in a Series for easier handling
        sig_series = pd.Series(raw_signal, index=prices.index)
        prev_sig_series = sig_series.shift(1)
        
        # Define events: Crossover
        # Cross UP: prev was -1, now 1
        # Cross DOWN: prev was 1, now -1
        
        # Filter where they are different
        events_mask = (sig_series != prev_sig_series) & (sig_series != 0) & (prev_sig_series != 0)
        # Clean up initial NaNs
        events_mask.iloc[:self.slow_window] = False
        
        events = sig_series[events_mask]
        
        # Return format expected: DataFrame with 'side'
        # The 'events' series index gives us the timestamps.
        # The values give us the side.
        
        return pd.DataFrame({
            'side': events,
        }, index=events.index)
