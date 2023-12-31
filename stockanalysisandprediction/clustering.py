import json

import pandas as pd
from django.http import JsonResponse
from rest_framework.decorators import api_view
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from stockanalysisandprediction.models import Stock, APICache
from stockanalysisandprediction.views_analytics import get_cached_response


@api_view(["GET"])
def makeCluster(request):
    time = request.GET.get("time", "1_week")
    params = {"time": time}
    cached_response = get_cached_response("makeCluster", params)
    if cached_response is not None:
        return JsonResponse(cached_response, safe=False)

    stock_tickers = pd.Series(Stock.objects.values("name").distinct()).apply(
        lambda x: x["name"]
    )
    combined_df = pd.DataFrame()

    for stock_ticker in stock_tickers:
        stock_data = Stock.objects.filter(name=stock_ticker).values()
        stock_data = pd.DataFrame(list(stock_data)).set_index("date")

        if len(stock_data) < 252:
            continue

        stock_data["Daily_Returns"] = stock_data["close"].pct_change()
        stock_data["Risk"] = stock_data["Daily_Returns"].rolling(window=22).std()

        time_values = {
            "all_time": len(stock_data),
            "1_week": 5,
            "2_weeks": 10,
            "1_month": 22,
            "1_quarter": 66,
            "6_months": 132,
            "1_year": 253,
        }

        if time.startswith("custom"):
            time_value = int(time[7:])
            time = "custom"
            time_values["custom"] = time_value

        stock_data = stock_data.tail(time_values[time])

        combined_df = pd.concat(
            [combined_df, stock_data[["name", "Daily_Returns", "Risk"]]]
        )

    combined_df.fillna(method="bfill", inplace=True)

    # Extract relevant features for clustering
    features = combined_df[["Daily_Returns", "Risk"]]

    # Standardize the features to have zero mean and unit variance
    scaler = StandardScaler()
    features_standardized = scaler.fit_transform(features)

    # K-Means Clustering
    num_clusters = 5
    kmeans = KMeans(n_clusters=num_clusters, random_state=42)
    combined_df["cluster"] = kmeans.fit_predict(features_standardized)
    centroids = scaler.inverse_transform(kmeans.cluster_centers_)

    combined_df.index = pd.to_datetime(combined_df.index)

    cluster_df = combined_df.groupby("name").last()

    cluster_df = cluster_df[["Daily_Returns", "Risk", "cluster"]]
    cluster_df = cluster_df.reset_index()

    data = {
        "cluster_df": cluster_df.to_dict(orient="records"),
        "centroids": centroids.tolist(),
    }

    APICache.objects.create(
        api_name="makeCluster",
        params=json.dumps(params, sort_keys=True),
        response=data,
    )

    return JsonResponse(
        data,
        safe=False,
    )
