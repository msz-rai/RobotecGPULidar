// Copyright 2023 Robotec.AI
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <cuda.h>
#include <curand_kernel.h>
#include <gpu/kernelUtils.hpp>
#include <gpu/gaussianNoiseKernels.hpp>

__global__ void kAddGaussianNoiseAngularRay(size_t rayCount, float mean, float stDev, rgl_axis_t rotationAxis,
                                            Mat3x4f lookAtOriginTransform, curandStatePhilox4_32_10_t* randomStates,
                                            const Mat3x4f* inRays, Mat3x4f* outRays)
{
	LIMIT(rayCount);

	float angularError = mean + curand_normal(&randomStates[tid]) * stDev;
	outRays[tid] = lookAtOriginTransform.inverse() *
	               (Mat3x4f::rotationRad(rotationAxis, angularError) * (lookAtOriginTransform * inRays[tid]));
}

__global__ void kAddGaussianNoiseAngularHitpoint(size_t pointCount, float mean, float stDev, rgl_axis_t rotationAxis,
                                                 Mat3x4f lookAtOriginTransform, curandStatePhilox4_32_10_t* randomStates,
                                                 const Field<XYZ_VEC3_F32>::type* inPoints,
                                                 Field<XYZ_VEC3_F32>::type* outPoints, Field<DISTANCE_F32>::type* outDistances)
{
	LIMIT(pointCount);

	float angularError = mean + curand_normal(&randomStates[tid]) * stDev;
	Field<XYZ_VEC3_F32>::type originWithNoisePoint = Mat3x4f::rotationRad(rotationAxis, angularError) *
	                                                 (lookAtOriginTransform * inPoints[tid]);

	if (outDistances != nullptr) {
		outDistances[tid] = originWithNoisePoint.length();
	}

	outPoints[tid] = lookAtOriginTransform.inverse() * originWithNoisePoint;
}

__global__ void kAddGaussianNoiseDistance(size_t pointCount, float mean, float stDevBase, float stDevRisePerMeter,
                                          Mat3x4f lookAtOriginTransform, curandStatePhilox4_32_10_t* randomStates,
                                          const Field<XYZ_VEC3_F32>::type* inPoints,
                                          const Field<DISTANCE_F32>::type* inDistances, Field<XYZ_VEC3_F32>::type* outPoints,
                                          Field<DISTANCE_F32>::type* outDistances)
{
	LIMIT(pointCount);

	float distanceInducedStDev = inDistances[tid] * stDevRisePerMeter;
	float totalStDev = distanceInducedStDev + stDevBase;
	float distanceError = mean + curand_normal(&randomStates[tid]) * totalStDev;

	Field<XYZ_VEC3_F32>::type pointInRayOriginTransform = lookAtOriginTransform * inPoints[tid];

	outPoints[tid] = lookAtOriginTransform.inverse() *
	                 (pointInRayOriginTransform + pointInRayOriginTransform.normalize() * distanceError);
	outDistances[tid] = inDistances[tid] + distanceError;
}

void gpuAddGaussianNoiseAngularRay(cudaStream_t stream, size_t rayCount, float mean, float stDev, rgl_axis_t rotationAxis,
                                   Mat3x4f lookAtOriginTransform, curandStatePhilox4_32_10_t* randomStates,
                                   const Mat3x4f* inRays, Mat3x4f* outRays)
{
	run(kAddGaussianNoiseAngularRay, stream, rayCount, mean, stDev, rotationAxis, lookAtOriginTransform, randomStates, inRays,
	    outRays);
}

void gpuAddGaussianNoiseAngularHitpoint(cudaStream_t stream, size_t pointCount, float mean, float stDev,
                                        rgl_axis_t rotationAxis, Mat3x4f lookAtOriginTransform,
                                        curandStatePhilox4_32_10_t* randomStates, const Field<XYZ_VEC3_F32>::type* inPoints,
                                        Field<XYZ_VEC3_F32>::type* outPoints, Field<DISTANCE_F32>::type* outDistances)
{
	run(kAddGaussianNoiseAngularHitpoint, stream, pointCount, mean, stDev, rotationAxis, lookAtOriginTransform, randomStates,
	    inPoints, outPoints, outDistances);
}

void gpuAddGaussianNoiseDistance(cudaStream_t stream, size_t pointCount, float mean, float stDevBase, float stDevRisePerMeter,
                                 Mat3x4f lookAtOriginTransform, curandStatePhilox4_32_10_t* randomStates,
                                 const Field<XYZ_VEC3_F32>::type* inPoints, const Field<DISTANCE_F32>::type* inDistances,
                                 Field<XYZ_VEC3_F32>::type* outPoints, Field<DISTANCE_F32>::type* outDistances)
{
	run(kAddGaussianNoiseDistance, stream, pointCount, mean, stDevBase, stDevRisePerMeter, lookAtOriginTransform, randomStates,
	    inPoints, inDistances, outPoints, outDistances);
}