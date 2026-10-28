"""Creates synthetic retail data (no real customers or private information)."""
from pathlib import Path
import numpy as np
import pandas as pd


def generate(dest=None, n=640):
    rng=np.random.default_rng(42)
    dates=pd.date_range('2025-01-01','2025-12-27',freq='D')
    products=np.array(['Frozen Chicken','French Fries','Nuggets','Fish Ball','Sausage'])
    regions=np.array(['Surabaya','Sidoarjo','Gresik','Malang'])
    product = rng.choice(products,n,p=[.30,.20,.25,.15,.10])
    quantity=rng.integers(1,8,n)
    unit_price=pd.Series(product).map({'Frozen Chicken':38000,'French Fries':26000,'Nuggets':33000,
                                      'Fish Ball':28000,'Sausage':22000}).to_numpy(dtype=float)
    unit_price += rng.choice([0,1000,2000],n)
    dates_col=rng.choice(dates,n).astype('datetime64[D]').astype(str)
    region=rng.choice(regions,n).astype(object)
    # Intentional imperfections for quality and cleaning demonstrations.
    region[::37]=None
    region[1::41]=' Surabaya '
    unit_price[::31]=np.nan
    revenue = quantity * unit_price
    df=pd.DataFrame({'order_id':[f'ORD-{i:05d}' for i in range(n)],'order_date':dates_col,
                     'product':product,'region':region, 'quantity':quantity,
                     'unit_price':unit_price,'revenue':revenue})
    df=pd.concat([df,df.iloc[10:15].copy()],ignore_index=True)
    dest=Path(dest or Path(__file__).resolve().parent/'data'/'sales_demo.csv')
    dest.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(dest,index=False)
    print(f'Generated {len(df)} synthetic rows at {dest}')
    return dest


if __name__=='__main__':
    generate()
