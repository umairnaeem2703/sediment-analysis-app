import math
import pandas as pd
import matplotlib.pyplot as plt

class FractionalModel:
    def __init__(self):
        self.g = 9.81              
        self.rho_w = 1000.0        
        self.rho_s = 2650.0        
        self.s = self.rho_s / self.rho_w 
        
        self.d50 = 0.02            
        self.f_s = 0.10            
        self.manning_n = 0.05      
        self.bed_width = 50.0      
        self.depth = 0.5           
        self.fractions = []

    def calculate_hydraulics(self, q_flow: float):
        if q_flow <= 0:
            return 0.0, 0.0
        area = self.bed_width * self.depth
        velocity = q_flow / area
        tau = (self.rho_w * self.g * (self.manning_n ** 2) * (velocity ** 2)) / math.pow(self.depth, 1.0/3.0)
        u_star = math.sqrt(tau / self.rho_w)
        return tau, u_star

    def calculate_dimensionless_transport(self, phi: float) -> float:
        if phi <= 0:
            return 0.0
        if phi < 1.35:
            return 0.002 * math.pow(phi, 7.5)
        else:
            return 14.0 * math.pow((1.0 - (0.894 / phi)), 4.5)

    def compute_daily_fractional_transport(self, q_flow: float):
        tau, u_star = self.calculate_hydraulics(q_flow)
        if tau == 0.0:
            return 0.0
        total_q_b = 0.0
        for frac in self.fractions:
            phi = tau / frac['tau_ri']
            w_star_i = self.calculate_dimensionless_transport(phi)
            q_bi = (w_star_i * frac['Fi'] * math.pow(u_star, 3)) / ((self.s - 1.0) * self.g)
            total_q_b += q_bi
        return total_q_b

    def load_fractional_parameters(self, df: pd.DataFrame):
        self.fractions = []
        for _, row in df.iterrows():
            fraction_data = {
                'di': float(row['di']),         
                'Fi': float(row['Fi']),         
                'bi': float(row['bi']),         
                'tau_ri': float(row['tau_ri'])  
            }
            self.fractions.append(fraction_data)

class TimeSeriesAggregator:
    def __init__(self, model: FractionalModel):
        self.model = model

    def process_annual_averages(self, df_flow: pd.DataFrame) -> pd.DataFrame:
        df_flow['Date'] = pd.to_datetime(df_flow['Date'])
        df_flow['Year'] = df_flow['Date'].dt.year
        df_flow['Daily_Bedload'] = df_flow['Flow'].apply(self.model.compute_daily_fractional_transport)
        
        annual_summary = df_flow.groupby('Year').agg(
            Annual_Average_Flow=('Flow', 'mean'),
            Annual_Average_Bedload=('Daily_Bedload', 'mean')
        )
        return annual_summary

class BedloadVisualizer:
    def __init__(self):
        plt.style.use('default')

    def generate_trend_graph(self, df_summary: pd.DataFrame):
        if df_summary.empty:
            raise ValueError("Dataframe is empty. Cannot generate plot.")
        fig, ax1 = plt.subplots(figsize=(10, 6))
        years = df_summary.index
        ax1.plot(years, df_summary['Annual_Average_Flow'], color='blue', marker='o', label='Average Flow')
        ax1.set_xlabel('Year', fontweight='bold')
        ax1.set_ylabel('Annual Average Flow (m³/s)', color='blue', fontweight='bold')
        ax1.tick_params(axis='y', labelcolor='blue')
        ax1.grid(True, linestyle='--', alpha=0.6)

        ax2 = ax1.twinx()  
        ax2.plot(years, df_summary['Annual_Average_Bedload'], color='red', marker='s', label='Average Bedload')
        ax2.set_ylabel('Annual Average Bedload (m³/s)', color='red', fontweight='bold')
        ax2.tick_params(axis='y', labelcolor='red')

        plt.title('Annual Flow vs. Bedload Transport Trends', fontweight='bold', pad=15)
        fig.tight_layout()
        return fig