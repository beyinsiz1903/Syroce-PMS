"""
Pagination and Query Optimization Utilities
Ensures efficient data retrieval for large datasets
"""

from typing import TypeVar, Generic, List, Dict, Any, Optional
from pydantic import BaseModel
from math import ceil

T = TypeVar('T')


class PaginationParams(BaseModel):
    """Standard pagination parameters"""
    page: int = 1
    page_size: int = 50
    
    def get_skip(self) -> int:
        """Calculate skip value for MongoDB"""
        return (self.page - 1) * self.page_size
    
    def get_limit(self) -> int:
        """Get limit value"""
        return self.page_size
    
    def validate(self):
        """Validate pagination parameters"""
        if self.page < 1:
            self.page = 1
        if self.page_size < 1:
            self.page_size = 1
        if self.page_size > 1000:  # Maximum page size
            self.page_size = 1000


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response format"""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
    
    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        page: int,
        page_size: int
    ):
        """Create paginated response"""
        total_pages = ceil(total / page_size) if page_size > 0 else 0
        
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1
        )


class QueryOptimizer:
    """Optimize MongoDB queries for performance"""
    
    @staticmethod
    def optimize_projection(fields: List[str] = None) -> Dict[str, int]:
        """
        Create optimal projection for MongoDB query
        Always exclude _id by default, include only necessary fields
        """
        if fields is None:
            return {'_id': 0}
        
        projection = {'_id': 0}
        for field in fields:
            projection[field] = 1
        
        return projection
    
    @staticmethod
    def add_tenant_filter(query: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
        """Always add tenant_id filter for multi-tenancy"""
        query['tenant_id'] = tenant_id
        return query
    
    @staticmethod
    def optimize_date_range(
        query: Dict[str, Any],
        field: str,
        start_date: Optional[Any],
        end_date: Optional[Any]
    ) -> Dict[str, Any]:
        """Add optimized date range filter"""
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter['$gte'] = start_date
            if end_date:
                date_filter['$lte'] = end_date
            
            if date_filter:
                query[field] = date_filter
        
        return query
    
    @staticmethod
    def optimize_text_search(
        query: Dict[str, Any],
        field: str,
        search_term: Optional[str]
    ) -> Dict[str, Any]:
        """Add case-insensitive text search"""
        if search_term:
            query[field] = {'$regex': search_term, '$options': 'i'}
        
        return query
    
    @staticmethod
    def optimize_sort(sort_field: str, sort_order: str = 'desc') -> List[tuple]:
        """Create optimized sort specification"""
        order = -1 if sort_order.lower() == 'desc' else 1
        return [(sort_field, order)]
    
    @staticmethod
    def get_common_projections() -> Dict[str, Dict[str, int]]:
        """Pre-defined projections for common queries"""
        return {
            'booking_list': {
                '_id': 0,
                'booking_id': 1,
                'guest_name': 1,
                'room_number': 1,
                'check_in': 1,
                'check_out': 1,
                'status': 1,
                'total_amount': 1,
                'created_at': 1
            },
            'room_list': {
                '_id': 0,
                'room_id': 1,
                'room_number': 1,
                'room_type': 1,
                'floor': 1,
                'status': 1,
                'price': 1
            },
            'guest_list': {
                '_id': 0,
                'guest_id': 1,
                'name': 1,
                'surname': 1,
                'email': 1,
                'phone': 1,
                'vip_status': 1
            },
            'folio_list': {
                '_id': 0,
                'folio_id': 1,
                'folio_number': 1,
                'booking_id': 1,
                'folio_type': 1,
                'balance': 1,
                'status': 1,
                'created_at': 1
            }
        }


class AggregationOptimizer:
    """Optimize MongoDB aggregation pipelines"""
    
    @staticmethod
    def add_tenant_match(pipeline: List[Dict], tenant_id: str) -> List[Dict]:
        """Add tenant filter as first stage"""
        pipeline.insert(0, {'$match': {'tenant_id': tenant_id}})
        return pipeline
    
    @staticmethod
    def add_pagination(
        pipeline: List[Dict],
        skip: int,
        limit: int
    ) -> List[Dict]:
        """Add pagination stages to pipeline"""
        pipeline.extend([
            {'$skip': skip},
            {'$limit': limit}
        ])
        return pipeline
    
    @staticmethod
    def add_count_stage(pipeline: List[Dict]) -> List[Dict]:
        """Add count stage for total calculation"""
        count_pipeline = pipeline.copy()
        count_pipeline.append({
            '$count': 'total'
        })
        return count_pipeline
    
    @staticmethod
    def optimize_lookup(
        from_collection: str,
        local_field: str,
        foreign_field: str,
        as_field: str,
        project_fields: List[str] = None
    ) -> Dict:
        """Create optimized $lookup stage"""
        lookup = {
            '$lookup': {
                'from': from_collection,
                'localField': local_field,
                'foreignField': foreign_field,
                'as': as_field
            }
        }
        
        # Add projection to lookup if specified
        if project_fields:
            lookup['$lookup']['pipeline'] = [
                {'$project': {field: 1 for field in project_fields}}
            ]
        
        return lookup


# Pre-built optimized queries

class OptimizedQueries:
    """Collection of pre-optimized query patterns"""
    
    @staticmethod
    def get_bookings_query(
        tenant_id: str,
        status: Optional[str] = None,
        check_in_start: Optional[Any] = None,
        check_in_end: Optional[Any] = None,
        room_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Optimized bookings query"""
        query = {'tenant_id': tenant_id}
        
        if status:
            query['status'] = status
        
        if check_in_start or check_in_end:
            date_filter = {}
            if check_in_start:
                date_filter['$gte'] = check_in_start
            if check_in_end:
                date_filter['$lte'] = check_in_end
            query['check_in'] = date_filter
        
        if room_id:
            query['room_id'] = room_id
        
        return query
    
    @staticmethod
    def get_rooms_available_query(
        tenant_id: str,
        check_in: Any,
        check_out: Any,
        room_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Aggregation pipeline for available rooms"""
        pipeline = [
            {'$match': {'tenant_id': tenant_id}},
        ]
        
        if room_type:
            pipeline[0]['$match']['room_type'] = room_type
        
        # Look for conflicting bookings
        pipeline.extend([
            {
                '$lookup': {
                    'from': 'bookings',
                    'let': {'room_id': '$room_id'},
                    'pipeline': [
                        {
                            '$match': {
                                '$expr': {
                                    '$and': [
                                        {'$eq': ['$room_id', '$$room_id']},
                                        {'$eq': ['$tenant_id', tenant_id]},
                                        {
                                            '$in': [
                                                '$status',
                                                ['confirmed', 'guaranteed', 'checked_in']
                                            ]
                                        },
                                        {
                                            '$or': [
                                                {
                                                    '$and': [
                                                        {'$lte': ['$check_in', check_in]},
                                                        {'$gt': ['$check_out', check_in]}
                                                    ]
                                                },
                                                {
                                                    '$and': [
                                                        {'$lt': ['$check_in', check_out]},
                                                        {'$gte': ['$check_out', check_out]}
                                                    ]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            }
                        }
                    ],
                    'as': 'conflicting_bookings'
                }
            },
            {
                '$match': {
                    'conflicting_bookings': {'$size': 0}
                }
            },
            {
                '$project': {
                    '_id': 0,
                    'room_id': 1,
                    'room_number': 1,
                    'room_type': 1,
                    'floor': 1,
                    'price': 1,
                    'status': 1
                }
            }
        ])
        
        return pipeline
    
    @staticmethod
    def get_dashboard_stats_pipeline(
        tenant_id: str,
        start_date: Any,
        end_date: Any
    ) -> Dict[str, List[Dict]]:
        """Optimized pipelines for dashboard statistics"""
        return {
            'occupancy': [
                {
                    '$match': {
                        'tenant_id': tenant_id,
                        'check_in': {'$lte': end_date},
                        'check_out': {'$gte': start_date},
                        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'total_bookings': {'$sum': 1},
                        'total_revenue': {'$sum': '$total_amount'}
                    }
                }
            ],
            'revenue_by_type': [
                {
                    '$match': {
                        'tenant_id': tenant_id,
                        'created_at': {
                            '$gte': start_date,
                            '$lte': end_date
                        }
                    }
                },
                {
                    '$group': {
                        '_id': '$charge_category',
                        'total': {'$sum': '$total'}
                    }
                }
            ]
        }


# Helper functions for common patterns

async def paginated_find(
    collection,
    query: Dict[str, Any],
    page: int,
    page_size: int,
    sort_field: str = 'created_at',
    sort_order: str = 'desc',
    projection: Dict[str, int] = None
):
    """
    Execute paginated find query
    
    Args:
        collection: MongoDB collection
        query: Query filter
        page: Page number (1-indexed)
        page_size: Items per page
        sort_field: Field to sort by
        sort_order: 'asc' or 'desc'
        projection: Fields to include/exclude
    
    Returns:
        PaginatedResponse
    """
    # Validate pagination
    params = PaginationParams(page=page, page_size=page_size)
    params.validate()
    
    # Get total count
    total = await collection.count_documents(query)
    
    # Get items
    if projection is None:
        projection = {'_id': 0}
    
    sort_spec = QueryOptimizer.optimize_sort(sort_field, sort_order)
    
    items = await collection.find(
        query,
        projection
    ).sort(
        sort_spec
    ).skip(
        params.get_skip()
    ).limit(
        params.get_limit()
    ).to_list(params.get_limit())
    
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size
    )


async def execute_optimized_aggregation(
    collection,
    pipeline: List[Dict],
    page: int = None,
    page_size: int = None
):
    """
    Execute aggregation pipeline with optional pagination
    
    Args:
        collection: MongoDB collection
        pipeline: Aggregation pipeline
        page: Page number for pagination
        page_size: Items per page
    
    Returns:
        Results and total count if paginated
    """
    if page and page_size:
        # Get total count
        count_pipeline = AggregationOptimizer.add_count_stage(pipeline.copy())
        count_result = await collection.aggregate(count_pipeline).to_list(1)
        total = count_result[0]['total'] if count_result else 0
        
        # Add pagination
        params = PaginationParams(page=page, page_size=page_size)
        params.validate()
        
        paginated_pipeline = AggregationOptimizer.add_pagination(
            pipeline,
            params.get_skip(),
            params.get_limit()
        )
        
        items = await collection.aggregate(paginated_pipeline).to_list(params.get_limit())
        
        return PaginatedResponse.create(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size
        )
    else:
        # No pagination
        results = await collection.aggregate(pipeline).to_list(None)
        return results
